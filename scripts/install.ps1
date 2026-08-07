param([string]$Python = "python", [int]$Port = 47831)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path (Join-Path $Root "runtime") | Out-Null
$start = Join-Path $PSScriptRoot "start.ps1"
$run = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$start`" -Python `"$Python`" -Port $Port"
New-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Force | Out-Null
New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name Plotkeeper -Value $run -PropertyType String -Force | Out-Null
$healthy = $false
try { $healthy = (Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2).ok -eq $true } catch {}
if (-not $healthy) {
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $start, "-Python", $Python, "-Port", "$Port")
    for ($attempt = 0; $attempt -lt 20 -and -not $healthy; $attempt++) {
        Start-Sleep -Milliseconds 250
        try { $healthy = (Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2).ok -eq $true } catch {}
    }
}
if (-not $healthy) { throw "Plotkeeper did not become healthy on port $Port." }
Write-Output "Plotkeeper installed, running, and registered for user startup."
