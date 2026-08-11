param([string]$Python = "", [int]$Port = 47831)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
if (-not $Python) {
    $localPython = Join-Path $Root ".venv\Scripts\python.exe"
    $Python = if (Test-Path $localPython) { $localPython } else { "python" }
}

function Get-ListenerPid {
    try {
        $connection = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
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

function Test-Dashboard {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/" -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content -match '(?is)<html(?:\s|>)' -and $response.Content -match 'data-testid=["'']plotkeeper-app["'']'
    } catch { return $false }
}

$listener = Get-ListenerPid
if ($listener) {
    if (Test-Dashboard) { return }
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

& $Python -m plotkeeper.cli serve --host 127.0.0.1 --port $Port
