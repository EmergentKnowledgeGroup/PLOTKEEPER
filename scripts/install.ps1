param(
    [string]$Python = "python", [int]$Port = 0, [switch]$NoStartup, [string]$Sessions = "",
    [string]$InstallRoot = "", [switch]$StopOnly, [string]$WheelPath = "",
    [string]$StartupRegistryPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run",
    [string]$StartupSnapshotPath = ""
)
$ErrorActionPreference = "Stop"
$Root = if ($InstallRoot) { [IO.Path]::GetFullPath($InstallRoot) } else { [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)) }
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
        if ($priorListener -and -not (Test-PlotkeeperOwner $priorListener ([int]$priorOwner.port))) {
            throw "Prior Plotkeeper port is occupied by an unknown or foreign listener; refusing to stop or reuse it."
        }
    }
}

if ($StopOnly) {
    $savedOwner = Read-OwnerRecord
    $stopPorts = @()
    if ($Port -gt 0) { $stopPorts += $Port }
    if ($savedOwner) { $stopPorts += [int]$savedOwner.port }
    foreach ($stopPort in ($stopPorts | Select-Object -Unique)) {
        $ownedListener = Get-ListenerPid $stopPort
        if ($ownedListener) { Stop-OwnedListener $ownedListener $stopPort }
    }
    return
}

$start = Join-Path $Root "scripts\start.ps1"
$venv = Join-Path $Root ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
if (-not $NoStartup) {
    $startupKey = Get-Item -LiteralPath $StartupRegistryPath -ErrorAction SilentlyContinue
    $startupExisted = $startupKey -and ($startupKey.GetValueNames() -contains 'Plotkeeper')
    $previousStartup = if ($startupExisted) { $startupKey.GetValue('Plotkeeper', $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames) } else { $null }
    $previousStartupKind = if ($startupExisted) { [string]$startupKey.GetValueKind('Plotkeeper') } else { 'String' }
    $expectedStartupPrefix = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$start`" -Python `"$venvPython`" -Port "
    if ($startupExisted -and -not ([string]$previousStartup).StartsWith($expectedStartupPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Plotkeeper startup registration belongs to another command or checkout; refusing to overwrite it. Use -NoStartup to preserve it or review docs\AGENT_REPAIR.md."
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "runtime") | Out-Null
$installTempParent = Join-Path $Root "runtime\tmp\install"
$installTemp = Join-Path $installTempParent ([Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $installTemp | Out-Null
$priorTemp = $env:TEMP
$priorTmp = $env:TMP
$priorPipCache = $env:PIP_CACHE_DIR
try {
    $env:TEMP = $installTemp
    $env:TMP = $installTemp
    $env:PIP_CACHE_DIR = $installTemp
    if (-not (Test-Path $venvPython)) {
        & $Python -I -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw "Plotkeeper virtual environment creation failed; existing runtime state was preserved." }
    }
    if ($WheelPath) {
        if (-not (Test-Path -LiteralPath $WheelPath -PathType Leaf)) { throw "Plotkeeper wheel not found: $WheelPath" }
        & $venvPython -I -m pip install --disable-pip-version-check --force-reinstall --no-deps --no-index $WheelPath
    } else {
        # A clean build input prevents an earlier build/lib from reintroducing removed modules.
        $buildSource = Join-Path $installTemp "source"
        New-Item -ItemType Directory -Force -Path $buildSource | Out-Null
        Copy-Item -LiteralPath (Join-Path $Root "plotkeeper") -Destination $buildSource -Recurse
        foreach ($name in @("pyproject.toml", "README.md", "LICENSE")) {
            $sourceFile = Join-Path $Root $name
            if (Test-Path -LiteralPath $sourceFile) { Copy-Item -LiteralPath $sourceFile -Destination $buildSource }
        }
        & $venvPython -I -m pip install --disable-pip-version-check --force-reinstall --no-deps $buildSource
    }
    if ($LASTEXITCODE -ne 0) { throw "Plotkeeper package installation failed; connector, listener and startup state were preserved. Rerun scripts\install.ps1 after fixing the pip error." }
    & $venvPython -I -m plotkeeper.cli doctor --source-root $Root
    if ($LASTEXITCODE -ne 0) { throw "Plotkeeper installed/source verification failed; refusing to change connector, listener or startup state. See docs\AGENT_REPAIR.md and rerun scripts\install.ps1." }
} finally {
    $env:TEMP = $priorTemp
    $env:TMP = $priorTmp
    $env:PIP_CACHE_DIR = $priorPipCache
    if (Test-Path -LiteralPath $installTemp) {
        Remove-Item -LiteralPath $installTemp -Recurse -Force
    }
}
$priorOwner = Read-OwnerRecord
if ($priorOwner -and $Port -gt 0 -and [int]$priorOwner.port -ne $Port) {
    $priorListener = Get-ListenerPid ([int]$priorOwner.port)
    if ($priorListener) { Stop-OwnedListener $priorListener ([int]$priorOwner.port) }
}
$explicitPort = if ($Port -gt 0) { "$Port" } else { "0" }
$connectorJson = & $venvPython -I -c "import json,sys; from plotkeeper.connector import ensure_connector; port=int(sys.argv[2]); print(json.dumps(ensure_connector(sys.argv[1], port if port else None)))" $connectorPath $explicitPort
if ($LASTEXITCODE -ne 0) { throw "Plotkeeper connector selection failed." }
$connector = $connectorJson | ConvertFrom-Json
$Port = [int]$connector.port
$HostAddress = [string]$connector.host
if ($HostAddress -ne "127.0.0.1") { throw "Plotkeeper connector must remain loopback-only." }
$listener = Get-ListenerPid $Port
if ($listener) {
    Stop-OwnedListener $listener $Port
}
$run = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$start`" -Python `"$venvPython`" -Port $Port"
if ($Sessions) { $run += " -Sessions `"$Sessions`"" }
if (-not $NoStartup) {
    $currentKey = Get-Item -LiteralPath $StartupRegistryPath -ErrorAction SilentlyContinue
    $currentExisted = $currentKey -and ($currentKey.GetValueNames() -contains 'Plotkeeper')
    $currentStartup = if ($currentExisted) { $currentKey.GetValue('Plotkeeper', $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames) } else { $null }
    if ([bool]$currentExisted -ne [bool]$startupExisted -or ($currentExisted -and -not [StringComparer]::Ordinal.Equals([string]$currentStartup, [string]$previousStartup))) {
        throw 'Plotkeeper startup registration changed during installation; refusing to overwrite it.'
    }
    if ($StartupSnapshotPath) {
        @{schema='plotkeeper.startup-backup.v1'; target=$Root; registry_path=$StartupRegistryPath;
          existed=[bool]$startupExisted; previous_value=$previousStartup; previous_kind=$previousStartupKind;
          installed_value=$run} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $StartupSnapshotPath -Encoding UTF8
    }
    New-Item -Path $StartupRegistryPath -Force | Out-Null
    New-ItemProperty -Path $StartupRegistryPath -Name Plotkeeper -Value $run -PropertyType String -Force | Out-Null
}
function Test-Health {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        $payload = $response.Content | ConvertFrom-Json
        return $response.StatusCode -eq 200 -and $payload.ok -eq $true -and $payload.service -eq "plotkeeper"
    } catch { return $false }
}
$startArguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $start, "-Python", $venvPython, "-Port", "$Port")
if ($Sessions) { $startArguments += @("-Sessions", $Sessions) }
$quotedStartArguments = ($startArguments | ForEach-Object { '"' + ([string]$_).Replace('"', '\"') + '"' }) -join ' '
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList $quotedStartArguments
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
$startupStatus = if ($NoStartup) { "startup registration unchanged" } else { "registered for user startup" }
Write-Output "Plotkeeper installed, running, and $startupStatus at $($connector.url)."
