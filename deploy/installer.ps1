$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$server = 'ubuntu@129.213.23.39'
$key = Join-Path $env:USERPROFILE '.ssh\peretosh_bot.key'
$work = Join-Path $env:TEMP ('magnit-' + [Guid]::NewGuid().ToString('N'))
$remote = '/home/ubuntu/.magnit-stage-' + [Guid]::NewGuid().ToString('N')
$exitCode = 1
$secret = $null
$settings = @{}
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
    $inputBytes = [Text.Encoding]::UTF8.GetBytes($InputText + "`n")
    $proc.StandardInput.BaseStream.Write($inputBytes, 0, $inputBytes.Length)
    $proc.StandardInput.BaseStream.Flush()
    $proc.StandardInput.BaseStream.Close()
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
    Write-Host 'MAGNIT | Oracle startup repair' -ForegroundColor Green
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
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try { $bundleHash = [BitConverter]::ToString($sha256.ComputeHash([IO.File]::ReadAllBytes($bundle))).Replace('-','').ToLowerInvariant() }
    finally { $sha256.Dispose() }
    if ($bundleHash -ne '__BUNDLE_SHA256__') { throw 'Проверка целостности пакета не пройдена.' }
    Write-Host 'Подключаю Oracle. При первом подключении SSH покажет отпечаток ключа сервера.'
    & ssh.exe -i $key -o ConnectTimeout=15 $server 'true'
    if ($LASTEXITCODE -ne 0) { throw 'Нет SSH-доступа к Oracle.' }
    $null = Remote 'command -v python3; command -v git; sudo -n true; python3 -c "import sys,sqlite3; assert sys.version_info >= (3,10)"'
    if ($env:MAGNIT_CHECK_ONLY -eq '1') {
        Write-Host 'CHECK_ONLY_OK: bundle decoded, checksum matched, SSH and Python available.' -ForegroundColor Green
        $exitCode=0
        exit 0
    }
    $existing = Remote 'if sudo -n test -f /etc/magnit/config.json; then echo MAGNIT_CONFIG_PRESENT; fi'
    Start-Process 'https://t.me/BotFather'
    while ($true) {
        $secret = ReadHidden 'Вставь токен MagnitWaveBot (ввод скрыт; Enter сохраняет текущий токен при повторном запуске)'
        if (-not $secret -and $existing.Contains('MAGNIT_CONFIG_PRESENT')) { break }
        if ($secret -match '^[0-9]{5,16}:[A-Za-z0-9_-]{30,100}$') { $settings.token=$secret; break }
        Write-Host 'Формат токена не подходит. Возьми токен именно @MagnitWaveBot в BotFather.' -ForegroundColor Yellow
    }
    $null = Remote ('mkdir -m 700 ' + $remote)
    & scp.exe -i $key -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=yes $bundle ($server + ':' + $remote + '/release.bundle')
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось отправить встроенный пакет на сервер.' }
    Write-Host 'Проверяю тесты, делаю бэкап и запускаю МАГНИТ...' -ForegroundColor Green
    # Secret characters are ASCII. SSH receives the JSON only through stdin.
    $inputJson = $settings | ConvertTo-Json -Compress
    if ([string]::IsNullOrWhiteSpace($inputJson) -or -not $inputJson.TrimStart().StartsWith('{')) { throw 'CONFIG_INPUT_EMPTY: configuration was not serialized.' }
    $null = $inputJson | ConvertFrom-Json
    $result = Remote ('git clone --quiet --branch main ' + $remote + '/release.bundle ' + $remote + '/src && sudo -n python3 ' + $remote + '/src/deploy/install.py') $inputJson
    if ($result -notmatch 'DEPLOYED ([0-9a-f]{40})') { throw 'Сервер не подтвердил deployed.' }
    $deployed = $Matches[1]
    $tag = Remote 'git --git-dir=/home/ubuntu/git/magnit.git rev-parse deployed'
    if ($tag.Trim() -ne $deployed) { throw 'Тег deployed не совпадает с проверенным релизом.' }
    $docs=[Environment]::GetFolderPath('MyDocuments')
    Copy-Item -LiteralPath $bundle -Destination (Join-Path $docs 'MagnitMain.bundle') -Force
    $null = Remote ('python3 -c ' + "'import pathlib,shutil; p=pathlib.Path(" + '"' + $remote + '"' + " ).resolve(); assert p.parent == pathlib.Path(" + '"/home/ubuntu"' + " ) and p.name.startswith(" + '".magnit-stage-"' + " ); shutil.rmtree(p)'" )
    Write-Host ''
    Write-Host ('ГОТОВО. На сервере МАГНИТ, релиз ' + $deployed.Substring(0,12)) -ForegroundColor Green
    Write-Host 'Бэкап сделан. Тег deployed подтверждён. Копия кода: Документы\MagnitMain.bundle.'
    Write-Host 'Проверь в Telegram:'
    Write-Host '1. /start: должно появиться меню MAGNIT DEMO.'
    Write-Host '2. Открой демо-позицию, затем портфель и историю.'
    Write-Host '3. Нажми Русский / English для смены языка.'
    $healthCommand = 'python3 -c "import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen(''http://127.0.0.1:8769/health''))))"'
    $beforeHealth = (Remote $healthCommand).Trim() | ConvertFrom-Json
    $before = [long]$beforeHealth.replies
    Start-Process 'https://t.me/MagnitWaveBot'
    Write-Host 'Отправь /start в открытом Telegram. Проверяю настоящий ответ до 90 секунд...'
    $verified=$false
    for($attempt=0;$attempt -lt 18;$attempt++) {
        Start-Sleep -Seconds 5
        $probe = Remote $healthCommand
        $health = $probe.Trim() | ConvertFrom-Json
        if ($health.ok -and $health.revision -eq $deployed -and [long]$health.replies -gt $before) {
            Write-Host 'LIVE_REPLY_OK: Telegram подтвердил отправку ответа после входящего сообщения.' -ForegroundColor Green
            $verified=$true
            break
        }
    }
    if (-not $verified) { Write-Host 'Релиз работает. Ответ на новое сообщение пока не подтверждён. Отправь /start в Telegram.' -ForegroundColor Yellow }
    $exitCode=0
} catch {
    Write-Host ''
    Write-Host ('НЕ ЗАВЕРШЕНО: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Успешный запуск не заявлен. Это окно можно закрыть и повторить запуск.'
} finally {
    $secret=$null; $aiKey=$null; $inputJson=$null; $settings=$null
    $resolvedWork = [IO.Path]::GetFullPath($work)
    $tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    if (-not $resolvedWork.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Temporary path validation failed.' }
    if (Test-Path -LiteralPath $resolvedWork) { Remove-Item -LiteralPath $resolvedWork -Recurse -Force }
    if ($env:MAGNIT_CHECK_ONLY -ne '1') { Read-Host 'Нажми Enter, чтобы закрыть окно' | Out-Null }
}
exit $exitCode
