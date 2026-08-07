$ErrorActionPreference = "Stop"
$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Test-Path $key) { Remove-ItemProperty -Path $key -Name Plotkeeper -ErrorAction SilentlyContinue }
Write-Output "Plotkeeper startup registration removed. Runtime ledger was preserved."
