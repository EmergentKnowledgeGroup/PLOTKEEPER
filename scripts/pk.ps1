param(
    [Parameter(Position=0)][string]$Command = "status",
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments
)
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
Push-Location $root
try {
    $diagnostic = & $python -I -m plotkeeper.cli doctor --source-root $root
    if ($LASTEXITCODE -ne 0) {
        Write-Output $diagnostic
        throw "Plotkeeper installed/source verification failed. Rerun scripts\install.ps1; see docs\AGENT_REPAIR.md."
    }
    & $python -I -m plotkeeper.cli $Command @Arguments
    $commandExitCode = $LASTEXITCODE
} finally { Pop-Location }
exit $commandExitCode
