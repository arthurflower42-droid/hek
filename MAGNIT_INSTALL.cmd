@echo off
chcp 65001 >nul
setlocal
set "MAGNIT_SELF=%~f0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$t=[IO.File]::ReadAllText($env:MAGNIT_SELF); $m=[regex]::Match($t,'(?s)\r?\n:POWERSHELL\r?\n(.*?)\r?\n:END_POWERSHELL'); & ([scriptblock]::Create($m.Groups[1].Value))"
exit /b %errorlevel%
:POWERSHELL
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$server = 'ubuntu@129.213.23.39'
$key = Join-Path $env:USERPROFILE '.ssh\peretosh_bot.key'
$work = Join-Path $env:TEMP ('magnit-' + [Guid]::NewGuid().ToString('N'))
$remote = '/home/ubuntu/.magnit-stage-' + [Guid]::NewGuid().ToString('N')
$exitCode = 1
$secret = $null
function Remote([string]$Command, [string]$InputText = '') {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = (Get-Command ssh.exe).Source
    $info.Arguments = '-i "' + $key + '" -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=15 -o StrictHostKeyChecking=yes ' + $server + ' "' + $Command.Replace('"','\"') + '"'
    $info.UseShellExecute = $false
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $info.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $info
    if (-not $proc.Start()) { throw 'Не удалось запустить SSH.' }
    $stdout = $proc.StandardOutput.ReadToEndAsync()
    $stderr = $proc.StandardError.ReadToEndAsync()
    $proc.StandardInput.WriteLine($InputText)
    $proc.StandardInput.Close()
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while (-not $proc.WaitForExit(1000)) {
        if ($timer.Elapsed.TotalSeconds -gt 1200) {
            $proc.Kill()
            throw 'SSH не ответил за 20 минут. Повторный запуск проверит состояние сервера.'
        }
        if ([int]$timer.Elapsed.TotalSeconds % 20 -eq 0) { Write-Host 'Сервер работает, ожидаю завершения проверки...' }
    }
    $out = $stdout.GetAwaiter().GetResult()
    $err = $stderr.GetAwaiter().GetResult()
    if ($out) { Write-Host $out }
    if ($proc.ExitCode -ne 0) {
        if ($err) { Write-Host $err }
        throw ('Сервер вернул ошибку ' + $proc.ExitCode + '. Успех не подтверждён.')
    }
    return $out
}
function ReadHidden([string]$Title) {
    $secure = Read-Host $Title -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr); $secure.Dispose() }
}
try {
    Write-Host 'МАГНИТ | Тестовый релиз Артура' -ForegroundColor Green
    Write-Host 'Отдельный сервис. Данные и код других ботов не меняются.'
    if (-not (Test-Path -LiteralPath $key)) { throw ('Не найден SSH-ключ: ' + $key) }
    foreach ($tool in @('ssh.exe','scp.exe')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            Start-Process 'ms-settings:optionalfeatures'
            throw ('В Windows отсутствует ' + $tool + '. Открыты дополнительные компоненты: нужен Клиент OpenSSH.')
        }
    }
    New-Item -ItemType Directory -Path $work | Out-Null
    $bundle = Join-Path $work 'magnit.bundle'
    $raw = [IO.File]::ReadAllText($env:MAGNIT_SELF)
    $bundle64 = [regex]::Match($raw, '(?s)\r?\n:BUNDLE\r?\n(.*?)\r?\n:END_BUNDLE').Groups[1].Value
    if (-not $bundle64) { throw 'Встроенный пакет не найден.' }
    [IO.File]::WriteAllBytes($bundle,[Convert]::FromBase64String($bundle64))
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $bundle).Hash.ToLowerInvariant() -ne 'a8a60b1a18a8d876e1de94acb9d90a79b9aef2de7c3a0407b2dfd21216c2b920') { throw 'Проверка целостности пакета не пройдена.' }
    Write-Host 'Подключаю Oracle. При первом подключении SSH покажет отпечаток ключа сервера.'
    & ssh.exe -i $key -o ConnectTimeout=15 $server 'true'
    if ($LASTEXITCODE -ne 0) { throw 'Нет SSH-доступа к Oracle.' }
    $null = Remote 'command -v python3; command -v git; sudo -n true; python3 -c "import sys,sqlite3; assert sys.version_info >= (3,10)"'
    $existing = Remote 'if sudo -n test -f /etc/magnit/config.json; then echo MAGNIT_CONFIG_PRESENT; fi'
    $settings = @{}
    Start-Process 'https://t.me/BotFather'
    while ($true) {
        $secret = ReadHidden 'Вставь токен MagnitWaveBot (ввод скрыт; Enter сохраняет текущий токен при повторном запуске)'
        if (-not $secret -and $existing.Contains('MAGNIT_CONFIG_PRESENT')) { break }
        if ($secret -match '^[0-9]{5,16}:[A-Za-z0-9_-]{30,100}$') { $settings.token=$secret; break }
        Write-Host 'Формат токена не подходит. Возьми токен именно @MagnitWaveBot в BotFather.' -ForegroundColor Yellow
    }
    $addAI = Read-Host 'Подключить AI через отдельный API-ключ OpenAI? API оплачивается отдельно. y/д = да, Enter = пропустить'
    if ($addAI -match '^(y|yes|д|да)$') {
        Start-Process 'https://platform.openai.com/api-keys'
        $aiKey = ReadHidden 'Вставь API-ключ OpenAI (ввод скрыт)'
        if ([string]::IsNullOrWhiteSpace($aiKey)) { throw 'Ключ AI пустой. Повтори запуск или пропусти подключение AI.' }
        $model = Read-Host 'Модель API (Enter = gpt-5-mini)'
        if ([string]::IsNullOrWhiteSpace($model)) { $model='gpt-5-mini' }
        if ($model -notmatch '^[a-zA-Z0-9._-]{1,100}$') { throw 'Недопустимое имя модели.' }
        $settings.openai_key=$aiKey
        $settings.openai_model=$model
        $settings.ai_daily_limit=10
    }
    $null = Remote ('mkdir -m 700 ' + $remote)
    & scp.exe -i $key -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=yes $bundle ($server + ':' + $remote + '/release.bundle')
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось отправить встроенный пакет на сервер.' }
    Write-Host 'Проверяю тесты, делаю бэкап и запускаю МАГНИТ...' -ForegroundColor Green
    # JSON contains ASCII escapes only: Windows PowerShell cannot corrupt Cyrillic over stdin.
    $inputJson = $settings | ConvertTo-Json -Compress
    $result = Remote ('git clone --quiet ' + $remote + '/release.bundle ' + $remote + '/src && sudo -n python3 ' + $remote + '/src/deploy/install.py') $inputJson
    if ($result -notmatch 'DEPLOYED ([0-9a-f]{40})') { throw 'Сервер не подтвердил deployed.' }
    $deployed = $Matches[1]
    $tag = Remote 'git --git-dir=/home/ubuntu/git/magnit.git rev-parse deployed'
    if ($tag.Trim() -ne $deployed) { throw 'Тег deployed не совпадает с проверенным релизом.' }
    $docs=[Environment]::GetFolderPath('MyDocuments')
    Copy-Item -LiteralPath $bundle -Destination (Join-Path $docs 'MagnitMain.bundle') -Force
    $null = Remote ('rm -rf ' + $remote)
    Write-Host ''
    Write-Host ('ГОТОВО. На сервере МАГНИТ, релиз ' + $deployed.Substring(0,12)) -ForegroundColor Green
    Write-Host 'Бэкап сделан. Тег deployed подтверждён. Копия кода: Документы\MagnitMain.bundle.'
    Write-Host 'Проверь в Telegram:'
    Write-Host '1. /start, затем кнопки Крипта и Новости.'
    Write-Host '2. /music Daft Punk, открой найденный трек.'
    Write-Host '3. Настройки: смени валюту, затем снова открой Крипту.'
    Start-Process 'https://t.me/MagnitWaveBot'
    $exitCode=0
} catch {
    Write-Host ''
    Write-Host ('НЕ ЗАВЕРШЕНО: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Успешный запуск не заявлен. Это окно можно закрыть и повторить запуск.'
} finally {
    $secret=$null; $aiKey=$null; $inputJson=$null; $settings=$null
    if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
    Read-Host 'Нажми Enter, чтобы закрыть окно' | Out-Null
}
exit $exitCode

:END_POWERSHELL
:BUNDLE
IyB2MiBnaXQgYnVuZGxlCjY0NTM0M2FlZDFlNjY5MTI3NDk5Y2RlNDQxYTk0MDE5ODQ4NjhmN2Ig
cmVmcy9oZWFkcy9tYWluCjY0NTM0M2FlZDFlNjY5MTI3NDk5Y2RlNDQxYTk0MDE5ODQ4NjhmN2Ig
SEVBRAoKUEFDSwAAAAIAAAALnx14nJVPzUrDQBC+5ynmAWrJNrHRImKPPkbsbtpC20jYCt76A4JU
UfAioh58glgsbWKavsLMGzm7UdCjyzA7u9833zejE6XAF9KNvMD3xIEbCG9fik6kGlEYRUF0JoJQ
eE0pm0o64Vj34gTaie6NEzgK7X0yDLujvq4P4k44OAYRHHqNQPCBPdd3XacTD4d9rdV/+xx8xnt8
wBd8xLcW4A5XNMElLTADmmKKBZY0pRnnO84r/KQb3FYwPyvohz8xOG5wzbJPNKcJw4sa4NZQvnU2
NWNS4obVc8CC5rjm7twCW0wNiYVKzMwfmChxR1csWxr81wDt0zrgK2t+/J1rWu1gLMDE3Bqn1Rh0
zUo5VwX7vdMt16kdqLBeO+u9tAqGlYFU54P4Usk6L2XMmE+zFnT7GhJ1oRLtfAGPdgDDrw14nDM0
MDAzMVHQS88syUzPyy9KZZAo6lGVcbh51NZluvPi/xrvXn1dFmkIURXk6uji66qXm8Kg0xAYP1U2
18H5pfq2j27mS04EHDKCKkrKL9ErqGSQV3FVvmF8s8DJriKo7U7+FaGjX0NNDIBAISW1ICe/kkGU
8eRte/ebtdOsPupE+gc73Nqt/hNqRElqcUk81ByDL0LXAqqn1yplHDuXdWHzInmJZynIyiCmgVTK
3Xi4NFR/XuEVv70edWHdzUwvwzsAe6pW77MDeJyLjy+oTE5MzkiNj9fn0tIrLszJLEk11uJKzs9L
y0zXyyrOzwMKZ6dWAsmk0ryUnFQuAMPTENO7oAJ4nH1Y224bRxJ951cUYASIEXJISbvJWlgEkY3E
ESDFWktBgIWBYES2yYmoGYYzlKA3SYyjNZSVYmwegmxib5wfGNGiRVEU+Qs9f5RT1T0cXpJ9MEnN
dFdXnTp1qtp3SP+sv9f/0b/oH/XrXA7fQ91JTvU1JUc61gM9TI6SY3ye47Orb5Lv9K281qPkEGu7
up8ck/4+OUyOkzYexQ5tHES1wKclZ6H0Xp54t+zr6yGJsVjf6ksd8xb8ipNz0he6h383+BzKOX3Y
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

:END_BUNDLE
