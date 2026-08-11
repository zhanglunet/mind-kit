[CmdletBinding()]
param(
    [switch]$SelfCheck,
    [switch]$NoOpen,
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

function Find-Python {
    if (Test-Path $VenvPython) { return $VenvPython }
    foreach ($Candidate in @("py", "python", "python3")) {
        $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
        if (-not $Command) { continue }
        if ($Candidate -eq "py") {
            & py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)"
            if ($LASTEXITCODE -eq 0) { return "py -3" }
        } else {
            & $Candidate -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)"
            if ($LASTEXITCODE -eq 0) { return $Candidate }
        }
    }
    throw "需要 Python 3.9+。请先安装 Python，并在安装界面勾选 Add Python to PATH。"
}

$Python = Find-Python
$Arguments = @((Join-Path $Root "scripts\install_second_brain.py"))
if ($SelfCheck) { $Arguments += "--self-check" }
if ($NoOpen) { $Arguments += "--no-open" }
if ($Port -gt 0) { $Arguments += @("--port", "$Port") }

if ($Python -eq "py -3") {
    & py -3 @Arguments
} else {
    & $Python @Arguments
}
exit $LASTEXITCODE
