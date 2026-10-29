#!/usr/bin/env python3
"""Atomic release activation. Run as root; secrets arrive only on stdin."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT=Path('/opt/magnit')
DATA=Path('/var/lib/magnit')
CONFIG=Path('/etc/magnit/config.json')
REPO=Path('/home/ubuntu/git/magnit.git')
SOURCE=Path(__file__).resolve().parents[1]
UNIT=Path('/etc/systemd/system/magnit.service')
SERVICE='''[Unit]
Description=МАГНИТ Telegram bot
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=magnit
Group=magnit
WorkingDirectory=/var/lib/magnit
ExecStart=/usr/bin/python3 /opt/magnit/current/bot.py --config /etc/magnit/config.json
Restart=on-failure
RestartSec=5
TimeoutStopSec=55
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/magnit
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
[Install]
WantedBy=multi-user.target
'''

def run(*args, **kwargs):
    return subprocess.run(args,check=True,**kwargs)
def git(*args):
    return subprocess.check_output(['git','-C',str(SOURCE),*args],text=True).strip()
def atom(path, data, mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.new')
    temp.write_text(data)
    temp.chmod(mode)
    os.replace(temp,path)
def select(path):
    tmp=ROOT/'current.new'
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(path)
    os.replace(tmp,ROOT/'current')
def verify(config):
    # Credentials never appear in command arguments, diagnostics or git.
    token=config.get('token','')
    if not re.fullmatch(r'[0-9]{5,16}:[A-Za-z0-9_-]{30,100}',token):
        raise RuntimeError('Invalid Telegram token format')
    def api(method):
        url='https://api.telegram.org/bot'+token+'/'+method
        with urllib.request.urlopen(url,timeout=20) as response:
            body=json.load(response)
        if not body.get('ok'):
            raise RuntimeError('Telegram verification failed')
        return body['result']
    if api('getMe').get('username','').lower()!='magnitwavebot':
        raise RuntimeError('Token must belong to MagnitWaveBot')
    if api('getWebhookInfo').get('url'):
        raise RuntimeError('Bot already has a webhook. Existing configuration was preserved.')
    if config.get('openai_key'):
        request=urllib.request.Request('https://api.openai.com/v1/models/'+config.get('openai_model','gpt-5-mini'),
            headers={'Authorization':'Bearer '+config['openai_key']})
        with urllib.request.urlopen(request,timeout=20) as response:
            if response.status!=200:raise RuntimeError('AI model verification failed')

def main():
    if os.geteuid()!=0:raise RuntimeError('Use sudo -n python3')
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/'deploy.lock').open('w') as lock:
        print('Waiting for deployment lock...',flush=True)
        fcntl.flock(lock,fcntl.LOCK_EX)
        revision=git('rev-parse','HEAD')
        run(sys.executable,'-m','unittest','-q',cwd=SOURCE)
        run(sys.executable,str(SOURCE/'deploy/scan.py'),str(SOURCE))
        existing=json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
        supplied={} if '--existing' in sys.argv else json.load(sys.stdin)
        config={**existing,**supplied,'database':str(DATA/'magnit.sqlite3'),
                'revision':revision,'expected_username':'MagnitWaveBot','health_port':8769}
        verify(config)
        if subprocess.run(['id','magnit'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode != 0:
            run('useradd','--system','--home-dir',str(DATA),'--shell','/usr/sbin/nologin','magnit')
        DATA.mkdir(parents=True,exist_ok=True)
        run('chown','magnit:magnit',str(DATA))
        CONFIG.parent.mkdir(parents=True,exist_ok=True)
        run('chown','root:magnit',str(CONFIG.parent));CONFIG.parent.chmod(0o750)
        backup=ROOT/'backups'/(time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()%1000000000))
        backup.mkdir(parents=True,exist_ok=False);backup.chmod(0o700)
        old=Path(os.path.realpath(ROOT/'current')) if (ROOT/'current').exists() else None
        old_config=CONFIG.read_text() if CONFIG.exists() else None
        old_unit=UNIT.read_text() if UNIT.exists() else None
        was_active=subprocess.run(['systemctl','is-active','--quiet','magnit']).returncode==0
        if old_config:atom(backup/'config.json',old_config)
        if old_unit:atom(backup/'magnit.service',old_unit)
        if old:atom(backup/'release',str(old))
        # SQLite online backup is consistent even while the old process runs.
        if (DATA/'magnit.sqlite3').exists():
            with sqlite3.connect(DATA/'magnit.sqlite3') as src, sqlite3.connect(backup/'magnit.sqlite3') as dest:
                src.backup(dest)
        release=ROOT/'releases'/revision
        if not release.exists():
            stage=Path(tempfile.mkdtemp(prefix='release-',dir=ROOT))
            try:
                run('git','-C',str(SOURCE),'archive','--format=tar','-o',str(stage/'source.tar'),'HEAD')
                with tarfile.open(stage/'source.tar') as archive:
                    archive.extractall(stage/'src',filter='data')
                release.parent.mkdir(parents=True,exist_ok=True)
                os.replace(stage/'src',release)
            finally:shutil.rmtree(stage)
        try:
            # First stop: never run competing Telegram long-poll consumers.
            run('systemctl','stop','magnit') if UNIT.exists() else None
            atom(CONFIG,json.dumps(config,ensure_ascii=False,indent=2),0o640)
            run('chown','root:magnit',str(CONFIG))
            atom(UNIT,SERVICE,0o644)
            select(release)
            run('systemctl','daemon-reload')
            run('systemctl','enable','magnit',stdout=subprocess.DEVNULL)
            run('systemctl','restart','magnit')
            deadline=time.monotonic()+120
            healthy=False
            while time.monotonic()<deadline:
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8769/health',timeout=3) as response:
                        health=json.load(response)
                    healthy=health.get('ok') and health.get('revision')==revision
                    if healthy:break
                except Exception:pass
                time.sleep(2)
            if not healthy:raise RuntimeError('Health check did not confirm this release')
            REPO.parent.mkdir(parents=True,exist_ok=True)
            if not REPO.exists():run('git','init','--bare',str(REPO),stdout=subprocess.DEVNULL)
            atom(REPO/'hooks/post-receive',HOOK,0o755)
            # Commit is embedded in bundle. Updating main is a real push; hook skips recursive deploy.
            run('git','-C',str(SOURCE),'push',str(REPO),'HEAD:refs/heads/main',env={**os.environ,'MAGNIT_INSTALLING':'1'})
            run('git','--git-dir',str(REPO),'symbolic-ref','HEAD','refs/heads/main')
            run('git','--git-dir',str(REPO),'bundle','create',str(backup/'magnit.bundle'),'--all')
            run('chown','-R','ubuntu:ubuntu',str(REPO))
            run('sudo','-u','ubuntu','git','--git-dir',str(REPO),'tag','-f','deployed',revision)
            actual=subprocess.check_output(['git','-c','safe.directory='+str(REPO),'--git-dir',str(REPO),'rev-parse','deployed'],text=True).strip()
            if actual!=revision:raise RuntimeError('deployed tag mismatch')
            print('DEPLOYED '+revision,flush=True)
            print('BACKUP '+str(backup),flush=True)
        except Exception:
            subprocess.run(['systemctl','stop','magnit'])
            if old:select(old)
            else:(ROOT/'current').unlink(missing_ok=True)
            if old_config:
                atom(CONFIG,old_config,0o640);run('chown','root:magnit',str(CONFIG))
            else:CONFIG.unlink(missing_ok=True)
            if old_unit:atom(UNIT,old_unit,0o644)
            else:UNIT.unlink(missing_ok=True)
            run('systemctl','daemon-reload')
            if was_active and old:subprocess.run(['systemctl','start','magnit'])
            print('Deployment rolled back. Backup: '+str(backup),flush=True)
            raise

HOOK='''#!/bin/bash
set -euo pipefail
[ "${MAGNIT_INSTALLING:-}" = 1 ] && exit 0
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
while read -r old new ref; do
  if [ "$ref" = refs/heads/main ] && [ "$new" != 0000000000000000000000000000000000000000 ]; then
    stage=$(mktemp -d /home/ubuntu/.magnit-hook-XXXXXX)
    trap 'rm -rf "$stage"' EXIT
    git clone --quiet /home/ubuntu/git/magnit.git "$stage/src"
    git -C "$stage/src" checkout --quiet "$new"
    sudo -n python3 "$stage/src/deploy/install.py" --existing
  fi
done
'''
if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Only exception class: upstream exception text can contain credentials.
        print('Установка не завершена ('+type(exc).__name__+'). Предыдущий релиз сохранён или восстановлен.',file=sys.stderr)
        if isinstance(exc, RuntimeError):print(str(exc),file=sys.stderr)
        sys.exit(1)
