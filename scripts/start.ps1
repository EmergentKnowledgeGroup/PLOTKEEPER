param([string]$Python = "", [int]$Port = 47831)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
if (-not $Python) {
    $localPython = Join-Path $Root ".venv\Scripts\python.exe"
    $Python = if (Test-Path $localPython) { $localPython } else { "python" }
}
& $Python -m plotkeeper.cli serve --host 127.0.0.1 --port $Port
