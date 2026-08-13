param([string]$Python = "python", [int]$Port = 0)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path (Join-Path $Root "runtime") | Out-Null
$venv = Join-Path $Root ".venv"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    & $Python -m venv $venv
}
$venvPython = Join-Path $venv "Scripts\python.exe"
$installTemp = Join-Path $Root "runtime\tmp\install"
New-Item -ItemType Directory -Force -Path $installTemp | Out-Null
$priorTemp = $env:TEMP
$priorTmp = $env:TMP
$priorPipCache = $env:PIP_CACHE_DIR
try {
    $env:TEMP = $installTemp
    $env:TMP = $installTemp
    $env:PIP_CACHE_DIR = $installTemp
    & $venvPython -m pip install --disable-pip-version-check --upgrade $Root
} finally {
    $env:TEMP = $priorTemp
    $env:TMP = $priorTmp
    $env:PIP_CACHE_DIR = $priorPipCache
    if (Test-Path -LiteralPath $installTemp) {
        Remove-Item -LiteralPath $installTemp -Recurse -Force
    }
}
$connectorPath = Join-Path $Root "runtime\plotkeeper-connector.json"
$explicitPort = if ($Port -gt 0) { "$Port" } else { "" }
$connectorJson = & $venvPython -c "import json,sys; from plotkeeper.connector import ensure_connector; print(json.dumps(ensure_connector(sys.argv[1], int(sys.argv[2]) if sys.argv[2] else None)))" $connectorPath $explicitPort
if ($LASTEXITCODE -ne 0) { throw "Plotkeeper connector selection failed." }
$connector = $connectorJson | ConvertFrom-Json
$Port = [int]$connector.port
$HostAddress = [string]$connector.host
if ($HostAddress -ne "127.0.0.1") { throw "Plotkeeper connector must remain loopback-only." }
$start = Join-Path $PSScriptRoot "start.ps1"
$run = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$start`" -Python `"$venvPython`" -Port $Port"
New-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Force | Out-Null
New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name Plotkeeper -Value $run -PropertyType String -Force | Out-Null
function Test-Dashboard {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/" -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content -match '(?is)<html(?:\s|>)' -and $response.Content -match 'data-testid=["'']plotkeeper-app["'']'
    } catch { return $false }
}
function Get-ListenerPid([int]$TargetPort = $Port) {
    try {
        $connection = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort $TargetPort -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($connection) { return [int]$connection.OwningProcess }
    } catch { }
    return $null
}
function Get-OwnerCommandLine([int]$ListenerProcessId) {
    if (-not $ListenerProcessId) { return "" }
    try { return [string](Get-CimInstance Win32_Process -Filter "ProcessId=$ListenerProcessId" -ErrorAction Stop).CommandLine } catch { return "" }
}
function Test-PlotkeeperOwner([int]$ListenerProcessId) {
    $commandLine = Get-OwnerCommandLine $ListenerProcessId
    return $commandLine -match '(?i)(plotkeeper\.cli|plotkeeper[\\/]scripts[\\/]start\.ps1)'
}
$legacyPort = 47831
if ($Port -ne $legacyPort) {
    $legacyListener = Get-ListenerPid $legacyPort
    if ($legacyListener -and (Test-PlotkeeperOwner $legacyListener)) {
        Stop-Process -Id $legacyListener -Force -ErrorAction Stop
    }
}
$listener = Get-ListenerPid
if ($listener) {
    if (-not (Test-PlotkeeperOwner $listener)) {
        throw "Port $Port is occupied by a non-Plotkeeper listener; refusing to stop it."
    }
    Stop-Process -Id $listener -Force -ErrorAction Stop
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (-not (Get-ListenerPid)) { break }
        Start-Sleep -Milliseconds 100
    }
    if (Get-ListenerPid) { throw "Stale Plotkeeper listener on port $Port did not stop." }
}
$healthy = $false
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $start, "-Python", $venvPython, "-Port", "$Port")
for ($attempt = 0; $attempt -lt 40 -and -not $healthy; $attempt++) {
    Start-Sleep -Milliseconds 250
    $healthy = Test-Dashboard
}
if (-not $healthy) { throw "Plotkeeper did not become healthy on port $Port." }
Write-Output "Plotkeeper installed, running, and registered for user startup at $($connector.url)."
