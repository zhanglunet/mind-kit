[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$SelfCheck,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CompileArgs
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $Python) { throw "找不到 Python；请先运行 .\install-second-brain.ps1" }

$Arguments = @((Join-Path $Root "scripts\compile_second_brain.py"))
if ($DryRun) { $Arguments += "--dry-run" }
if ($SelfCheck) { $Arguments += "--self-check" }
if ($CompileArgs) { $Arguments += $CompileArgs }
& $Python @Arguments
exit $LASTEXITCODE
