param(
    [Parameter(Mandatory=$true)][string]$TargetRoot,
    [string]$BundleRoot = '',
    [ValidateSet('Install','Rollback')][string]$Action = 'Install',
    [string]$Backup,
    [switch]$NoStartup,
    [string]$Sessions,
    [string]$StartupRegistryPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
    [switch]$ConfirmInstall
)
$ErrorActionPreference = 'Stop'
# Windows PowerShell may inherit PowerShell 7's module search order from the
# calling agent. Load the matching built-ins, not a different shell's manifest.
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1') -Force
Import-Module (Join-Path $PSHOME 'Modules/Microsoft.PowerShell.Security/Microsoft.PowerShell.Security.psd1') -Force
if (-not $BundleRoot) { $BundleRoot = $PSScriptRoot }
$TargetRoot = [IO.Path]::GetFullPath($TargetRoot).TrimEnd('\','/')
$BundleRoot = [IO.Path]::GetFullPath($BundleRoot)
if ($TargetRoot -eq [IO.Path]::GetPathRoot($TargetRoot).TrimEnd('\','/') -or
    $TargetRoot -eq $BundleRoot -or $TargetRoot.StartsWith($BundleRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose a dedicated Plotkeeper installation directory, not a drive root or the installer bundle.'
}

function Resolve-Child([string]$Base, [string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative)) { throw 'Absolute manifest path rejected.' }
    $path = [IO.Path]::GetFullPath((Join-Path $Base $Relative))
    if (-not $path.StartsWith($Base.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Manifest path escapes its root.' }
    $part = $path
    while ($part -and $part.Length -ge $Base.Length) {
        if ((Test-Path -LiteralPath $part) -and ((Get-Item -LiteralPath $part -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Linked path rejected: $part" }
        $part = Split-Path -Parent $part
    }
    return $path
}

function Restore-Backup([string]$Saved) {
    $record = Get-Content -LiteralPath (Join-Path $Saved 'backup.json') -Raw | ConvertFrom-Json
    if (-not [StringComparer]::OrdinalIgnoreCase.Equals([string]$record.target, $TargetRoot)) { throw 'Backup belongs to another installation.' }
    $restoredMarker = Join-Path $Saved 'rollback-complete'
    if (Test-Path -LiteralPath $restoredMarker) {
        Write-Host 'This backup was already restored; no startup, source or environment changes were made.'
        return
    }
    $startupSnapshot = Join-Path $Saved 'startup.json'
    if (-not $NoStartup -and (Test-Path -LiteralPath $startupSnapshot)) {
        $startup = Get-Content -LiteralPath $startupSnapshot -Raw | ConvertFrom-Json
        if ($startup.schema -ne 'plotkeeper.startup-backup.v1' -or
            -not [StringComparer]::OrdinalIgnoreCase.Equals([string]$startup.target, $TargetRoot) -or
            -not [StringComparer]::OrdinalIgnoreCase.Equals([string]$startup.registry_path, $StartupRegistryPath)) {
            throw 'Startup backup belongs to another installation or registry key.'
        }
        $startupKey = Get-Item -LiteralPath $StartupRegistryPath -ErrorAction SilentlyContinue
        $currentExists = $startupKey -and ($startupKey.GetValueNames() -contains 'Plotkeeper')
        $currentValue = if ($currentExists) { $startupKey.GetValue('Plotkeeper', $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames) } else { $null }
        $currentKind = if ($currentExists) { [string]$startupKey.GetValueKind('Plotkeeper') } else { $null }
        $alreadyPrevious = [bool]$currentExists -eq [bool]$startup.existed -and
            (-not $currentExists -or ([StringComparer]::Ordinal.Equals([string]$currentValue, [string]$startup.previous_value) -and $currentKind -eq $startup.previous_kind))
        if (-not $alreadyPrevious) {
            if (-not $currentExists -or -not [StringComparer]::Ordinal.Equals([string]$currentValue, [string]$startup.installed_value)) {
                throw 'Plotkeeper startup registration changed after installation; refusing rollback over a foreign entry.'
            }
            if ($startup.existed) {
                New-ItemProperty -LiteralPath $StartupRegistryPath -Name Plotkeeper -Value $startup.previous_value -PropertyType $startup.previous_kind -Force | Out-Null
            } else {
                Remove-ItemProperty -LiteralPath $StartupRegistryPath -Name Plotkeeper
            }
        }
    }
    # Stop only the target listener using the new, exact-identity stop route.
    & (Join-Path $BundleRoot 'source/scripts/install.ps1') -InstallRoot $TargetRoot -StopOnly
    $failedEnv = Resolve-Child $TargetRoot '.venv'
    if (Test-Path -LiteralPath $failedEnv) { Move-Item -LiteralPath $failedEnv -Destination (Join-Path $Saved ('replaced-venv-' + [guid]::NewGuid().ToString('N'))) }
    if (Test-Path -LiteralPath (Join-Path $Saved 'venv')) { Move-Item -LiteralPath (Join-Path $Saved 'venv') -Destination $failedEnv }
    foreach ($entry in $record.files) {
        $destination = Resolve-Child $TargetRoot $entry.path
        if ($entry.existed) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
            Copy-Item -LiteralPath (Resolve-Child (Join-Path $Saved 'source') $entry.path) -Destination $destination -Force
        } elseif (Test-Path -LiteralPath $destination) {
            # Only files introduced by this manifest are removed, never directories.
            Remove-Item -LiteralPath $destination -Force
        }
    }
    Set-Content -LiteralPath $restoredMarker -Value 'Restored; do not apply this backup twice.' -Encoding UTF8
    Write-Host "Previous source and environment restored. Runtime data was NOT overwritten. Backup: $Saved"
    Write-Host 'The restored service is stopped. Start it explicitly after reviewing the rollback.'
}

if (-not $ConfirmInstall) {
    Write-Host "Plotkeeper: $TargetRoot"
    Write-Host 'Save work first. This replaces only the owned Plotkeeper listener; LP will NOT be opened or closed.'
    Write-Host '1 - Install / repair (recommended)'
    Write-Host '2 - Restore a prior backup (service remains stopped)'
    Write-Host '0 - Cancel (Enter cancels)'
    $choice = Read-Host 'Choose 1, 2 or 0'
    if ($choice -eq '2') { $Action = 'Rollback'; if (-not $Backup) { $Backup = Read-Host 'Backup directory' } }
    elseif ($choice -ne '1') { return }
}
if ($Action -eq 'Rollback') { Restore-Backup ([IO.Path]::GetFullPath($Backup)); return }

$manifest = Get-Content -LiteralPath (Join-Path $BundleRoot 'manifest.json') -Raw | ConvertFrom-Json
if ($manifest.schema -ne 'plotkeeper.installer.v1') { throw 'Unsupported installer manifest.' }
$payload = Join-Path $BundleRoot 'source'
foreach ($entry in $manifest.files) {
    $source = Resolve-Child $payload $entry.path
    $null = Resolve-Child $TargetRoot $entry.path
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw "Payload hash mismatch: $($entry.path)" }
}
$wheel = Resolve-Child $BundleRoot $manifest.wheel.path
if ((Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.wheel.sha256) { throw 'Wheel hash mismatch.' }
$installMarker = Resolve-Child $TargetRoot 'runtime/plotkeeper-install.json'
if ((Test-Path -LiteralPath $TargetRoot) -and -not (Test-Path -LiteralPath (Join-Path $TargetRoot 'plotkeeper/cli.py'))) {
    $knownTarget = $false
    if (Test-Path -LiteralPath $installMarker) {
        $marker = Get-Content -LiteralPath $installMarker -Raw | ConvertFrom-Json
        $knownTarget = $marker.schema -eq 'plotkeeper.install.v1' -and
            [StringComparer]::OrdinalIgnoreCase.Equals([string]$marker.target, $TargetRoot)
    }
    if (-not $knownTarget -and (Get-ChildItem -LiteralPath $TargetRoot -Force | Select-Object -First 1)) { throw 'Nonempty target is not a Plotkeeper checkout or a marked interrupted installation.' }
}
$backupParent = Join-Path (Split-Path -Parent $TargetRoot) 'Plotkeeper-upgrade-backups'
$null = Resolve-Child (Split-Path -Parent $TargetRoot) 'Plotkeeper-upgrade-backups'
$Saved = Join-Path $backupParent ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Saved | Out-Null
$acl = New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in @([Security.Principal.WindowsIdentity]::GetCurrent().User, (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))) {
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
}
Set-Acl -LiteralPath $Saved -AclObject $acl
$records = @()
foreach ($entry in $manifest.files) {
    $existing = Resolve-Child $TargetRoot $entry.path
    $present = Test-Path -LiteralPath $existing
    $records += @{path=$entry.path; existed=$present}
    if ($present) {
        $savedFile = Resolve-Child (Join-Path $Saved 'source') $entry.path
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $savedFile) | Out-Null
        Copy-Item -LiteralPath $existing -Destination $savedFile
    }
}
@{target=$TargetRoot; files=$records; version=$manifest.version} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Saved 'backup.json') -Encoding UTF8
# Keep only this target-bound repair marker through rollback; runtime remains private.
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $installMarker) | Out-Null
@{schema='plotkeeper.install.v1'; target=$TargetRoot} | ConvertTo-Json | Set-Content -LiteralPath $installMarker -Encoding UTF8
& (Join-Path $payload 'scripts/install.ps1') -InstallRoot $TargetRoot -StopOnly
$oldEnv = Resolve-Child $TargetRoot '.venv'
if (Test-Path -LiteralPath $oldEnv) { Move-Item -LiteralPath $oldEnv -Destination (Join-Path $Saved 'venv') }
try {
    foreach ($entry in $manifest.files) {
        $destination = Resolve-Child $TargetRoot $entry.path
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath (Resolve-Child $payload $entry.path) -Destination $destination -Force
    }
    $installOptions = @{WheelPath=$wheel; NoStartup=$NoStartup; StartupRegistryPath=$StartupRegistryPath}
    if (-not $NoStartup) { $installOptions.StartupSnapshotPath = Join-Path $Saved 'startup.json' }
    if ($Sessions) { $installOptions.Sessions = $Sessions }
    & (Join-Path $TargetRoot 'scripts/install.ps1') @installOptions
    Write-Host "Plotkeeper $($manifest.version) installed and verified. Reversible backup: $Saved"
} catch {
    $failure = $_
    try { Restore-Backup $Saved } catch { Write-Warning "Automatic restore could not complete. Preserve backup: $Saved" }
    throw $failure
}
