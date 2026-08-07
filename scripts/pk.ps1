param(
    [Parameter(Position=0)][string]$Command = "status",
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments
)
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try { & python -m plotkeeper.cli $Command @Arguments } finally { Pop-Location }
