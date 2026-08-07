param([string]$Python = "python", [int]$Port = 47831)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
& $Python -m plotkeeper.cli serve --host 127.0.0.1 --port $Port
