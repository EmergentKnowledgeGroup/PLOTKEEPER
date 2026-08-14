param([string]$Python = "python", [int]$Port = 0)
$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$connectorPath = [IO.Path]::GetFullPath((Join-Path $Root "runtime\plotkeeper-connector.json"))
$ownerPath = [IO.Path]::GetFullPath((Join-Path $Root "runtime\plotkeeper-owner.json"))

function Get-ListenerPid([int]$TargetPort = $Port) {
    try {
        $connection = Get-NetTCPConnection -State Listen -LocalPort $TargetPort -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($connection) { return [int]$connection.OwningProcess }
    } catch { }
    return $null
}

function Get-ProcessIdentity([int]$ListenerProcessId) {
    if (-not $ListenerProcessId) { return $null }
    try { return Get-CimInstance Win32_Process -Filter "ProcessId=$ListenerProcessId" -ErrorAction Stop | Select-Object -First 1 } catch { return $null }
}

function Get-TextSha256([string]$Text) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes([string]$Text)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    } finally { $sha.Dispose() }
}

function Test-SamePath([string]$Left, [string]$Right) {
    try { return [StringComparer]::OrdinalIgnoreCase.Equals([IO.Path]::GetFullPath($Left), [IO.Path]::GetFullPath($Right)) } catch { return $false }
}

function Get-CreationTimeUtcTicks($Value) {
    if ($null -eq $Value) { return $null }
    if ($Value -is [DateTime]) { return ([DateTime]$Value).ToUniversalTime().Ticks }
    $parsed = [DateTime]::MinValue
    if ([DateTime]::TryParse([string]$Value, [Globalization.CultureInfo]::CurrentCulture, [Globalization.DateTimeStyles]::AssumeLocal, [ref]$parsed)) {
        return $parsed.ToUniversalTime().Ticks
    }
    $formats = @("o", "MM/dd/yyyy HH:mm:ss", "M/d/yyyy H:mm:ss", "MM/dd/yyyy hh:mm:ss tt", "M/d/yyyy h:mm:ss tt")
    foreach ($format in $formats) {
        if ([DateTime]::TryParseExact([string]$Value, $format, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeLocal, [ref]$parsed)) {
            return $parsed.ToUniversalTime().Ticks
        }
    }
    return $null
}

function Test-CreationTimeMatch($IdentityValue, $RecordValue) {
    $identityTicks = Get-CreationTimeUtcTicks $IdentityValue
    $recordTicks = Get-CreationTimeUtcTicks $RecordValue
    if ($null -eq $identityTicks -or $null -eq $recordTicks) { return $false }
    $exactRecord = [DateTime]::MinValue
    if ([DateTime]::TryParseExact([string]$RecordValue, "o", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind, [ref]$exactRecord)) {
        return $identityTicks -eq $recordTicks
    }
    $second = [TimeSpan]::TicksPerSecond
    return ($identityTicks - ($identityTicks % $second)) -eq ($recordTicks - ($recordTicks % $second))
}

function Read-OwnerRecord {
    if (-not (Test-Path -LiteralPath $ownerPath)) { return $null }
    try { return Get-Content -LiteralPath $ownerPath -Raw | ConvertFrom-Json } catch { return $null }
}

function Test-PlotkeeperOwner([int]$ListenerProcessId, [int]$TargetPort = $Port) {
    $record = Read-OwnerRecord
    $identity = Get-ProcessIdentity $ListenerProcessId
    if (-not $record -or -not $identity) { return $false }
    if ([int]$record.port -ne $TargetPort) { return $false }
    if ([string]$record.host -ne "127.0.0.1" -or -not (Test-SamePath ([string]$record.root) $Root) -or -not (Test-SamePath ([string]$record.connector_path) $connectorPath)) { return $false }
    $recordIdentity = $identity
    if ([int]$record.pid -ne $ListenerProcessId) {
        if ([int]$identity.ParentProcessId -ne [int]$record.pid) { return $false }
        $recordIdentity = Get-ProcessIdentity ([int]$record.pid)
        if (-not $recordIdentity) { return $false }
        if ((Get-TextSha256 ([string]$identity.CommandLine)) -ne [string]$record.command_line_sha256) { return $false }
    }
    if (-not (Test-SamePath ([string]$recordIdentity.ExecutablePath) ([string]$record.executable))) { return $false }
    if (-not (Test-CreationTimeMatch $recordIdentity.CreationDate $record.creation_time)) { return $false }
    if ((Get-TextSha256 ([string]$recordIdentity.CommandLine)) -ne [string]$record.command_line_sha256) { return $false }
    return $true
}

function Remove-OwnerRecord([int]$ListenerProcessId) {
    $record = Read-OwnerRecord
    if ($record -and [int]$record.pid -eq $ListenerProcessId -and (Test-SamePath ([string]$record.root) $Root)) {
        Remove-Item -LiteralPath $ownerPath -Force -ErrorAction SilentlyContinue
    }
}

function Stop-OwnedListener([int]$ListenerProcessId, [int]$TargetPort = $Port) {
    if (-not (Test-PlotkeeperOwner $ListenerProcessId $TargetPort)) { throw "Port $TargetPort is occupied by an unknown or foreign listener; refusing to stop or reuse it." }
    Stop-Process -Id $ListenerProcessId -Force -ErrorAction Stop
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (-not (Get-ListenerPid $TargetPort)) { break }
        Start-Sleep -Milliseconds 100
    }
    if (Get-ListenerPid $TargetPort) { throw "Stale Plotkeeper listener on port $TargetPort did not stop." }
    Remove-OwnerRecord $ListenerProcessId
}

# An explicit port lets us reject a foreign listener before venv, pip, registry,
# connector, or service work can mutate anything. This is also the test seam.
if ($Port -gt 0) {
    $earlyListener = Get-ListenerPid $Port
    if ($earlyListener -and -not (Test-PlotkeeperOwner $earlyListener $Port)) {
        throw "Port $Port is occupied by an unknown or foreign listener; refusing to stop or reuse it."
    }
    $priorOwner = Read-OwnerRecord
    if ($priorOwner -and [int]$priorOwner.port -ne $Port) {
        $priorListener = Get-ListenerPid ([int]$priorOwner.port)
        if ($priorListener) { Stop-OwnedListener $priorListener ([int]$priorOwner.port) }
    }
}

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
$explicitPort = if ($Port -gt 0) { "$Port" } else { "0" }
$connectorJson = & $venvPython -c "import json,sys; from plotkeeper.connector import ensure_connector; port=int(sys.argv[2]); print(json.dumps(ensure_connector(sys.argv[1], port if port else None)))" $connectorPath $explicitPort
if ($LASTEXITCODE -ne 0) { throw "Plotkeeper connector selection failed." }
$connector = $connectorJson | ConvertFrom-Json
$Port = [int]$connector.port
$HostAddress = [string]$connector.host
if ($HostAddress -ne "127.0.0.1") { throw "Plotkeeper connector must remain loopback-only." }
$listener = Get-ListenerPid $Port
if ($listener) {
    Stop-OwnedListener $listener $Port
}
$start = Join-Path $PSScriptRoot "start.ps1"
$run = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$start`" -Python `"$venvPython`" -Port $Port"
New-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Force | Out-Null
New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name Plotkeeper -Value $run -PropertyType String -Force | Out-Null
function Test-Health {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        $payload = $response.Content | ConvertFrom-Json
        return $response.StatusCode -eq 200 -and $payload.ok -eq $true -and $payload.service -eq "plotkeeper"
    } catch { return $false }
}
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $start, "-Python", $venvPython, "-Port", "$Port")
$healthy = $false
for ($attempt = 0; $attempt -lt 40 -and -not $healthy; $attempt++) {
    Start-Sleep -Milliseconds 250
    $healthy = Test-Health
}
if (-not $healthy) { throw "Plotkeeper did not become healthy on port $Port." }
$owned = $false
for ($attempt = 0; $attempt -lt 40 -and -not $owned; $attempt++) {
    $listener = Get-ListenerPid $Port
    if ($listener) { $owned = Test-PlotkeeperOwner $listener $Port }
    if (-not $owned) { Start-Sleep -Milliseconds 100 }
}
if (-not $owned) { throw "Plotkeeper became healthy on port $Port but did not publish a valid owner record." }
Write-Output "Plotkeeper installed, running, and registered for user startup at $($connector.url)."
