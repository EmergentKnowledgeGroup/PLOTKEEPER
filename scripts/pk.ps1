param(
    [Parameter(Position=0)][string]$Command = "status",
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments
)
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
Push-Location $root
try { & $python -m plotkeeper.cli $Command @Arguments } finally { Pop-Location }
