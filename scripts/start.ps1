param([string]$Python = "", [int]$Port = 0)
$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $Root
$localPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not $Python) {
    $Python = if (Test-Path $localPython) { $localPython } else { "python" }
}
$connectorPath = [IO.Path]::GetFullPath((Join-Path $Root "runtime\plotkeeper-connector.json"))
$ownerPath = [IO.Path]::GetFullPath((Join-Path $Root "runtime\plotkeeper-owner.json"))
if ($Port -le 0) {
    if (-not (Test-Path -LiteralPath $connectorPath)) {
        $connectorJson = & $Python -m plotkeeper.cli --ledger (Join-Path $Root "runtime\plotkeeper.sqlite3") connector
        if ($LASTEXITCODE -ne 0) { throw "Plotkeeper could not allocate its loopback connector." }
        $null = $connectorJson | ConvertFrom-Json
    }
    $connector = Get-Content -LiteralPath $connectorPath -Raw | ConvertFrom-Json
    if ([string]$connector.host -ne "127.0.0.1" -or [int]$connector.port -lt 1 -or [int]$connector.port -gt 65535) { throw "Plotkeeper connector is invalid; rerun scripts\install.ps1 with an explicit -Port if recovery is required." }
    $Port = [int]$connector.port
}

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
    if ([string]$RecordValue -match '^\d{4}-\d{2}-\d{2}T') { return $identityTicks -eq $recordTicks }
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
    if ([int]$record.pid -ne $ListenerProcessId -or [int]$record.port -ne $TargetPort) { return $false }
    if ([string]$record.host -ne "127.0.0.1" -or -not (Test-SamePath ([string]$record.root) $Root) -or -not (Test-SamePath ([string]$record.connector_path) $connectorPath)) { return $false }
    if (-not (Test-SamePath ([string]$identity.ExecutablePath) ([string]$record.executable))) { return $false }
    if (-not (Test-CreationTimeMatch $identity.CreationDate $record.creation_time)) { return $false }
    if ((Get-TextSha256 ([string]$identity.CommandLine)) -ne [string]$record.command_line_sha256) { return $false }
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

function Test-Health {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        $payload = $response.Content | ConvertFrom-Json
        return $response.StatusCode -eq 200 -and $payload.ok -eq $true -and $payload.service -eq "plotkeeper"
    } catch { return $false }
}

$priorOwner = Read-OwnerRecord
if ($priorOwner -and [int]$priorOwner.port -ne $Port) {
    $priorListener = Get-ListenerPid ([int]$priorOwner.port)
    if ($priorListener) { Stop-OwnedListener $priorListener ([int]$priorOwner.port) }
}
$listener = Get-ListenerPid
if ($listener) {
    if (Test-PlotkeeperOwner $listener) {
        if (Test-Health) { return }
        Stop-OwnedListener $listener
    } else {
        throw "Port $Port is occupied by an unknown or foreign listener; refusing to stop or reuse it."
    }
}

$ledgerPath = [IO.Path]::GetFullPath((Join-Path $Root "runtime\plotkeeper.sqlite3"))
$argumentList = @("-m", "plotkeeper.cli", "--ledger", $ledgerPath, "--connector", $connectorPath, "serve", "--host", "127.0.0.1", "--port", "$Port")
$quotedArguments = ($argumentList | ForEach-Object { $value = [string]$_; if ($value.IndexOf(' ') -ge 0 -or $value.IndexOf('"') -ge 0) { '"' + $value.Replace('"', '\"') + '"' } else { $value } }) -join ' '
$process = Start-Process -FilePath $Python -WorkingDirectory $Root -WindowStyle Hidden -ArgumentList $quotedArguments -PassThru
$identity = $null
for ($attempt = 0; $attempt -lt 20 -and -not $identity; $attempt++) {
    Start-Sleep -Milliseconds 100
    $identity = Get-ProcessIdentity $process.Id
}
if (-not $identity) { throw "Plotkeeper process identity could not be recorded." }
$owner = [ordered]@{
    version = 1
    pid = [int]$process.Id
    host = "127.0.0.1"
    port = [int]$Port
    root = $Root
    connector_path = $connectorPath
    executable = [string]$identity.ExecutablePath
    creation_time = ([DateTime]$identity.CreationDate).ToUniversalTime().ToString("o", [Globalization.CultureInfo]::InvariantCulture)
    command_line_sha256 = Get-TextSha256 ([string]$identity.CommandLine)
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ownerPath) | Out-Null
$ownerTemp = "$ownerPath.$PID.tmp"
$owner | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ownerTemp -Encoding UTF8
Move-Item -LiteralPath $ownerTemp -Destination $ownerPath -Force
try {
    $healthy = $false
    for ($attempt = 0; $attempt -lt 40 -and -not $healthy; $attempt++) {
        Start-Sleep -Milliseconds 250
        $healthy = Test-Health
    }
    if (-not $healthy) { throw "Plotkeeper did not become healthy on port $Port." }
    $process.WaitForExit()
} finally {
    Remove-OwnerRecord $process.Id
}
