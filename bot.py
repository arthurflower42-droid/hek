#!/usr/bin/env python3
"""МАГНИТ. Python 3.10+, standard library only."""
import argparse
import concurrent.futures
import datetime as dt
import html
import json
import logging
import math
import os
from pathlib import Path
import re
import signal
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = logging.getLogger('magnit')
COINS = {'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'TON': 'the-open-network'}
FEEDS = {'world': [('BBC', 'https://feeds.bbci.co.uk/russian/rss.xml')],
         'crypto': [('ForkLog', 'https://forklog.com/feed/')]}
COMMANDS = [('start', 'Главная'), ('portfolio', 'Мой портфель'), ('crypto', 'Курсы криптовалют'),
            ('news', 'Новости с источниками'), ('music', 'Поиск музыки'), ('settings', 'Мои настройки'),
            ('ai', 'AI-помощник'), ('privacy', 'Данные и приватность'), ('forget', 'Удалить мои настройки')]

def clean(value, limit=350):
    return html.escape(re.sub('<[^>]*>', '', html.unescape(str(value))).strip()[:limit])

def safe_url(value):
    p = urllib.parse.urlparse(value)
    return value if p.scheme == 'https' and p.netloc and not p.username else ''

class UpstreamError(Exception):
    def __init__(self, status=0, retry_after=0):
        self.status, self.retry_after = status, retry_after
        super().__init__('External service unavailable')

class HTTP:
    def request(self, url, data=None, headers=None, timeout=15, raw=False):
        h = {'User-Agent': 'MagnitWaveBot/1.0', **(headers or {})}
        body = None if data is None else json.dumps(data).encode()
        if body is not None:
            h['Content-Type'] = 'application/json'
        try:
            with urllib.request.urlopen(urllib.request.Request(url, body, h), timeout=timeout) as r:
                content = r.read(2_000_001)
                if len(content) > 2_000_000:
                    raise UpstreamError()
                return content if raw else json.loads(content)
        except urllib.error.HTTPError as exc:
            retry = 0
            try:
                payload = json.loads(exc.read(8192))
                retry = int(payload.get('parameters', {}).get('retry_after', 0))
            except (ValueError, TypeError):
                pass
            raise UpstreamError(exc.code, retry) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            raise UpstreamError() from None

class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, currency TEXT NOT NULL DEFAULT 'usd',
            topic TEXT NOT NULL DEFAULT 'world');
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS usage(user INTEGER, day TEXT, count INTEGER,
                PRIMARY KEY(user,day));
            CREATE TABLE IF NOT EXISTS holdings(user INTEGER, coin TEXT NOT NULL,
                amount REAL NOT NULL, PRIMARY KEY(user,coin));''')
        self.db.commit()
    def user(self, uid):
        self.db.execute('INSERT OR IGNORE INTO users(id) VALUES (?)', (uid,))
        self.db.commit()
        row = self.db.execute('SELECT currency,topic FROM users WHERE id=?', (uid,)).fetchone()
        return dict(zip(('currency', 'topic'), row))
    def setting(self, uid, key, value):
        allowed = {'currency': {'usd', 'rub', 'eur'}, 'topic': set(FEEDS)}
        if value not in allowed.get(key, set()):
            return False
        self.user(uid)
        self.db.execute('UPDATE users SET '+key+'=? WHERE id=?', (value, uid))
        self.db.commit()
        return True
    def forget(self, uid):
        self.db.execute('DELETE FROM users WHERE id=?', (uid,))
        self.db.execute('DELETE FROM usage WHERE user=?', (uid,))
        self.db.execute('DELETE FROM holdings WHERE user=?', (uid,))
        self.db.commit()
    def quota(self, uid, limit):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        self.db.execute('DELETE FROM usage WHERE day<?', (today,))
        row = self.db.execute('SELECT count FROM usage WHERE user=? AND day=?', (uid, today)).fetchone()
        if row and row[0] >= limit:
            self.db.commit()
            return False
        self.db.execute('INSERT INTO usage VALUES(?,?,1) ON CONFLICT(user,day) DO UPDATE SET count=count+1', (uid,today))
        self.db.commit()
        return True
    def holdings(self, uid):
        return {coin: amount for coin, amount in
                self.db.execute('SELECT coin,amount FROM holdings WHERE user=?', (uid,))}
    def add_holding(self, uid, coin, amount):
        self.db.execute('INSERT INTO holdings VALUES(?,?,?) ON CONFLICT(user,coin) DO UPDATE SET amount=amount+?', (uid,coin,amount,amount))
        self.db.commit()
    def remove_holding(self, uid, coin):
        self.db.execute('DELETE FROM holdings WHERE user=? AND coin=?', (uid,coin))
        self.db.commit()
    def offset(self, value=None):
        if value is not None:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('offset',?)", (str(value),))
            self.db.commit()
        row = self.db.execute("SELECT value FROM meta WHERE key='offset'").fetchone()
        return int(row[0]) if row else 0

class Bot:
    def __init__(self, config, http=None):
        self.cfg, self.http = config, http or HTTP()
        self.store = Store(config.get('database', 'magnit.sqlite3'))
        self.base = config.get('telegram_base', 'https://api.telegram.org') + '/bot' + config['token'] + '/'
        self.cache, self.rates = {}, {}
        self.last_poll = 0
        self.stopping = False
        self.revision = config.get('revision', 'local')
    def api(self, method, data=None, timeout=15):
        result = self.http.request(self.base+method, data or {}, timeout=timeout)
        if not result.get('ok'):
            raise UpstreamError(result.get('error_code', 0), result.get('parameters', {}).get('retry_after', 0))
        return result['result']
    def menu(self):
        return {'inline_keyboard': [
            [{'text': '◈ Крипта', 'callback_data': 'crypto'}, {'text': '◉ Новости', 'callback_data': 'news'}],
            [{'text': '◆ Портфель', 'callback_data': 'portfolio'}, {'text': '♫ Музыка', 'callback_data': 'music'}],
            [{'text': '✦ AI', 'callback_data': 'ai'}, {'text': '⚙ Настройки', 'callback_data': 'settings'}]]}
    def send(self, chat, text, markup=None):
        if len(text.encode('utf-16-le'))//2 > 3900:
            text = html.unescape(re.sub('<[^>]*>', '', text))[:1800]
            text = html.escape(text)
            if len(text.encode('utf-16-le'))//2 > 3900:
                return self.api('sendMessage', {'chat_id':chat, 'text':html.unescape(text)[:1800], 'reply_markup':markup or self.menu()})
        return self.api('sendMessage', {'chat_id': chat, 'text': text, 'parse_mode': 'HTML',
            'link_preview_options': {'is_disabled': True}, 'reply_markup': markup or self.menu()})
    def cached(self, key, ttl, load):
        now = time.monotonic()
        if key in self.cache and now-self.cache[key][0] < ttl:
            return self.cache[key][1]
        value = load()
        if len(self.cache) > 100:
            self.cache.clear()
        self.cache[key] = (now, value)
        return value
    def prices(self, currency):
        query = urllib.parse.urlencode({'ids': ','.join(COINS.values()), 'vs_currencies': currency,
            'include_24hr_change': 'true', 'include_last_updated_at': 'true'})
        base = self.cfg.get('price_base', 'https://api.coingecko.com/api/v3/simple/price')
        return self.cached('price:'+currency, 90, lambda: self.http.request(base+'?'+query))
    def crypto(self, prefs):
        currency = prefs['currency']
        data = self.prices(currency)
        lines = ['<b>◈ Рынок · '+currency.upper()+'</b>']
        stamps = []
        for symbol, coin in COINS.items():
            item = data.get(coin, {})
            price, change = item.get(currency), item.get(currency+'_24h_change')
            if not isinstance(price, (int, float)) or not math.isfinite(price):
                lines.append(symbol+' · нет данных')
                continue
            suffix = f'  {change:+.2f}% за 24 ч' if isinstance(change,(int,float)) and math.isfinite(change) else ''
            lines.append(f'<b>{symbol}</b>  {price:,.4f}'.rstrip('0').rstrip('.')+suffix)
            stamp = item.get('last_updated_at')
            if isinstance(stamp, (int,float)) and 0 < stamp < time.time()+3600:
                stamps.append(stamp)
        if not stamps:
            raise UpstreamError()
        oldest = min(stamps)
        when = dt.datetime.fromtimestamp(oldest, dt.timezone.utc).strftime('%d.%m %H:%M UTC')
        lines += ['', 'CoinGecko · '+when]
        if time.time()-oldest > 600:
            lines.append('⚠ Данные источника старше 10 минут.')
        return '\n'.join(lines)
    def portfolio(self, uid, prefs, arg):
        currency = prefs['currency']
        parts = arg.split()
        holdings = self.store.holdings(uid)
        if len(parts) >= 3 and parts[0].lower() in ('add','плюс','добавить'):
            coin = parts[1].upper()
            try:
                amount = float(parts[2].replace(',', '.'))
            except ValueError:
                amount = -1
            if coin not in COINS or not (math.isfinite(amount) and amount > 0):
                return 'Формат: <code>/portfolio add BTC 0.5</code>\nМонеты: '+', '.join(COINS)
            self.store.add_holding(uid, coin, amount)
            holdings = self.store.holdings(uid)
        elif len(parts) >= 2 and parts[0].lower() in ('del','remove','минус','убрать'):
            coin = parts[1].upper()
            if coin not in holdings:
                return f'{coin} нет в твоём портфеле.'
            self.store.remove_holding(uid, coin)
            holdings = self.store.holdings(uid)
        if not holdings:
            return ('<b>◆ Портфель пуст</b>\nЭто твой личный трекер: ты вносишь уже принадлежащие тебе монеты, '
                    'я показываю их рыночную стоимость по живым ценам CoinGecko.\n\n'
                    '<code>/portfolio add BTC 0.5</code> — добавить\n<code>/portfolio del BTC</code> — убрать')
        data = self.prices(currency)
        lines = ['<b>◆ Портфель · '+currency.upper()+'</b>', '']
        total, stamp = 0.0, 0
        for coin, amount in sorted(holdings.items()):
            item = data.get(COINS.get(coin, ''), {})
            price = item.get(currency)
            if not isinstance(price, (int, float)) or not math.isfinite(price):
                lines.append(f'  {coin}  {amount:g} · нет данных')
                continue
            value = amount * price
            total += value
            lines.append(f'  <b>{coin}</b>  {amount:g} ≈ {value:,.2f} {currency.upper()}')
            if isinstance(item.get('last_updated_at'), (int, float)):
                stamp = max(stamp, item['last_updated_at'])
        lines += ['', f'<b>Итого ≈ {total:,.2f} {currency.upper()}</b>']
        if stamp:
            lines += ['', 'CoinGecko · '+dt.datetime.fromtimestamp(stamp, dt.timezone.utc).strftime('%d.%m %H:%M UTC')]
        lines += ['', '<code>/portfolio add BTC 0.5</code> · <code>/portfolio del BTC</code>']
        return '\n'.join(lines)
    def feed(self, source):
        name, url = source
        raw = self.http.request(url, raw=True)
        root = ET.fromstring(raw)
        items = []
        for item in root.findall('.//item')[:8]:
            title, link = item.findtext('title',''), safe_url(item.findtext('link',''))
            date = clean(item.findtext('pubDate',''),70)
            if title and link:
                items.append(f'• <a href="{html.escape(link,quote=True)}">{clean(title,180)}</a>\n  {clean(name)} · {date}')
        return items[:5]
    def news(self, prefs):
        topic = prefs['topic']
        sources = self.cfg.get('feeds', FEEDS)[topic]
        def load():
            result = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                for future in [pool.submit(self.feed, s) for s in sources]:
                    try:
                        result.extend(future.result())
                    except (UpstreamError, ET.ParseError):
                        continue
            if not result:
                raise UpstreamError()
            return '\n\n'.join(result[:5])
        return '<b>◉ Новости · '+('Крипта' if topic=='crypto' else 'Мир')+'</b>\n\n'+self.cached('news:'+topic,180,load)
    def music(self, query):
        query = query.strip()[:120]
        if not query:
            return '♫ Напиши <code>/music исполнитель или трек</code>\nНапример: <code>/music Daft Punk</code>\nДам ссылки на найденные песни в Apple Music.'
        base = self.cfg.get('music_base', 'https://itunes.apple.com/search')
        data = self.cached('music:'+query.casefold(), 600, lambda: self.http.request(base+'?'+urllib.parse.urlencode(
            {'term':query, 'entity':'song', 'limit':5, 'country':'US'})))
        rows = []
        for item in data.get('results',[])[:5]:
            link = safe_url(item.get('trackViewUrl',''))
            if link:
                rows.append('♫ <a href="'+html.escape(link,quote=True)+'">'+clean(item.get('artistName',''),100)+' · '+clean(item.get('trackName',''),100)+'</a>')
        return '<b>Музыка · Apple Music</b>\n\n'+ ('\n\n'.join(rows) if rows else 'Ничего не найдено. Попробуй другое название.')
    def ai(self, uid, prompt):
        if not self.cfg.get('openai_key'):
            return '✦ AI пока не подключён. Владелец может подключить его повторным запуском установщика.\nКрипта, новости и музыка работают отдельно.'
        if not prompt:
            return '✦ Напиши <code>/ai твой вопрос</code>\nТекст запроса будет передан OpenAI для ответа. История переписки не отправляется. Не присылай пароли и ключи.'
        if not self.store.quota(uid, int(self.cfg.get('ai_daily_limit',10))):
            return 'Лимит AI на сегодня исчерпан. Попробуй завтра (сброс в 00:00 UTC).'
        result = self.http.request('https://api.openai.com/v1/responses', {
            'model': self.cfg.get('openai_model','gpt-5-mini'), 'store': False,
            'instructions': 'Ты помощник МАГНИТ. Отвечай по-русски, кратко. Не выдумывай актуальные новости, котировки или свои возможности. Для актуальных данных предложи /news или /crypto.',
            'input': prompt[:2000], 'max_output_tokens': 900},
            {'Authorization':'Bearer '+self.cfg['openai_key']}, timeout=45)
        text = '\n'.join(p.get('text','') for o in result.get('output',[]) for p in o.get('content',[]) if p.get('type')=='output_text')
        return clean(text,3500) if text else 'Модель не вернула текст. Попробуй более короткий вопрос.'
    def settings(self, prefs):
        return ('<b>⚙ Твои настройки</b>\nВалюта: '+prefs['currency'].upper()+'\nНовости: '+('Мир' if prefs['topic']=='world' else 'Крипта'),
            {'inline_keyboard': [
                [{'text': c.upper(), 'callback_data':'currency:'+c} for c in ('usd','rub','eur')],
                [{'text':'Мир', 'callback_data':'topic:world'}, {'text':'Крипта', 'callback_data':'topic:crypto'}],
                [{'text':'← Главная', 'callback_data':'start'}]]})
    def handle(self, update):
        cb = update.get('callback_query')
        message = cb.get('message',{}) if cb else update.get('message',{})
        user = (cb or message).get('from',{})
        uid, chat = user.get('id'), message.get('chat',{}).get('id')
        if cb:
            self.api('answerCallbackQuery', {'callback_query_id':cb['id']})
        if not uid or not chat or message.get('chat',{}).get('type') != 'private':
            return
        raw = cb.get('data','') if cb else message.get('text','')
        if not isinstance(raw,str):
            return
        # Bounded memory, one content request per two seconds per user.
        now = time.monotonic()
        if now-self.rates.get(uid, -100) < 2:
            return
        if len(self.rates)>10000:
            self.rates = {k:v for k,v in self.rates.items() if now-v < 60}
        self.rates[uid] = now
        command, _, arg = raw.strip().partition(' ')
        command = command.lstrip('/').split('@')[0].lower()
        if command=='forget':
            self.store.forget(uid)
            self.send(chat,'Твои настройки, портфель и счётчик AI удалены. При следующем обращении начнём заново.')
            return
        prefs = self.store.user(uid)
        if ':' in command:
            key,value = command.split(':',1)
            if self.store.setting(uid,key,value):
                prefs = self.store.user(uid)
                text, markup = self.settings(prefs)
                self.send(chat,text,markup)
            return
        try:
            if command in ('start','help'):
                text = ('<b>◆◆◆ ДОБРО ПОЖАЛОВАТЬ В МАГНИТ ◆◆◆</b>\n'
                        '<i>Крипта · Новости · Музыка · Портфель</i>\n\n'
                        '🎉 Ты в международном сообществе, где всё по-честному:\n'
                        'ни фейковых балансов, ни «оценочного дохода».\n\n'
                        '<b>◈ Крипта</b> — живые курсы с отметкой времени\n'
                        '<b>◆ Портфель</b> — твои реальные монеты по рыночным ценам\n'
                        '<b>◉ Новости</b> — только с первоисточниками\n'
                        '<b>♫ Музыка</b> и <b>✦ AI</b>\n\n'
                        'Выбирай раздел ниже.\n'
                        '<code>/privacy</code> — о данных · <code>/about</code> — о боте')
            elif command=='about':
                text = ('<b>◆ О МАГНИТЕ</b>\n\n'
                        'МАГНИТ — проект Артура. Это навигатор по рынку: курсы берутся у CoinGecko, '
                        'новости — у BBC и ForkLog, музыка — у Apple Music. '
                        'Бот не принимает деньги, не обещает доходность и не торгует за тебя.\n\n'
                        '<b>Презентация</b> = этот текст. Никаких «бизнес-моделей» — только полезные функции.')
            elif command=='portfolio':
                text = self.portfolio(uid, prefs, arg.strip())
            elif command=='crypto':
                text = self.crypto(prefs)
            elif command=='news':
                text = self.news(prefs)
            elif command=='music':
                text = self.music(arg)
            elif command=='ai':
                text = self.ai(uid,arg)
            elif command=='settings':
                text,markup = self.settings(prefs)
                self.send(chat,text,markup)
                return
            elif command=='privacy':
                text = 'Храним Telegram ID, валюту, тему новостей, состав портфеля и дневной счётчик AI. Тексты сообщений в базе не сохраняем.\n\nЗапросы /music отправляются Apple, /ai отправляются OpenAI, если AI подключён.\n\nУдалить настройки: /forget'
            else:
                text = 'Выбери раздел ниже. Портфель: <code>/portfolio add BTC 0.5</code>. Музыка: <code>/music название</code>. AI: <code>/ai вопрос</code>.'
        except (UpstreamError, ET.ParseError, KeyError, TypeError, ValueError):
            LOG.warning('content_unavailable command=%s', command if command in dict(COMMANDS) else 'other')
            text = 'Источник сейчас недоступен. Попробуй чуть позже или открой другой раздел. Выдуманные данные я не показываю.'
        self.send(chat,text)
    def setup(self):
        me = self.api('getMe')
        if me.get('username','').lower() != self.cfg.get('expected_username','MagnitWaveBot').lower():
            raise RuntimeError('Token belongs to another bot')
        webhook = self.api('getWebhookInfo')
        if webhook.get('url'):
            raise RuntimeError('Existing webhook found; installation stopped without changing it')
        self.api('setMyCommands', {'commands':[{'command':k,'description':v} for k,v in COMMANDS]})
        self.api('setMyDescription', {'description':'МАГНИТ: курсы криптовалют, портфель по живым ценам, новости с источниками, музыка и AI-помощник.'})
        self.api('setMyShortDescription', {'short_description':'Крипта · Портфель · Новости · Музыка. Твой ежедневный навигатор.'})
    def poll(self):
        updates = self.api('getUpdates', {'offset':self.store.offset(), 'timeout':30, 'allowed_updates':['message','callback_query']}, timeout=40)
        self.last_poll = time.monotonic()
        for update in updates:
            try:
                self.handle(update)
            except UpstreamError as exc:
                if exc.status in (400,403):
                    LOG.warning('undeliverable_update status=%s', exc.status)
                else:
                    raise
            self.store.offset(update['update_id']+1)
    def run(self):
        backoff = 1
        while not self.stopping:
            try:
                self.poll()
                backoff = 1
            except UpstreamError as exc:
                # Never log exception URLs; Telegram URLs contain credentials.
                LOG.warning('poll_failed status=%s',exc.status)
                if exc.status in (401,409):
                    raise RuntimeError('Unauthorized token or competing poller') from None
                time.sleep(min(60,max(backoff,exc.retry_after)))
                backoff = min(60,backoff*2)
    def health(self):
        return {'ok':bool(self.last_poll and time.monotonic()-self.last_poll<90), 'revision':self.revision}

def serve_health(bot, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/health':
                self.send_error(404)
                return
            result = bot.health()
            self.send_response(200 if result['ok'] else 503)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        def log_message(*args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config',default='/etc/magnit/config.json')
    parser.add_argument('--once',action='store_true',help='Process one poll, used by incoming-update harness')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    config = json.loads(Path(args.config).read_text())
    bot = Bot(config)
    bot.setup()
    if args.once:
        bot.poll()
        return
    server = serve_health(bot,int(config.get('health_port',8769)))
    signal.signal(signal.SIGTERM, lambda *_: setattr(bot,'stopping',True))
    signal.signal(signal.SIGINT, lambda *_: setattr(bot,'stopping',True))
    LOG.info('started revision=%s',bot.revision)
    try:
        bot.run()
    finally:
        server.shutdown()
        bot.store.db.close()

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        LOG.error('fatal type=%s',type(exc).__name__)
        raise SystemExit(1)
