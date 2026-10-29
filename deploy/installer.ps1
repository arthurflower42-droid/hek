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
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $bundle).Hash.ToLowerInvariant() -ne '__BUNDLE_SHA256__') { throw 'Проверка целостности пакета не пройдена.' }
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
