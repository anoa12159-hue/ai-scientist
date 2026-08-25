# AI Scientist MVP unified local verification entry (T001).
# Runs exactly the commands listed in tasks/TASK-001.md "Verification commands".
# Activate the project venv first, then run:
#   powershell -ExecutionPolicy Bypass -File scripts/verify_project.ps1
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "[verify] project root: $ProjectRoot"

# Gate: python 3.11+ on PATH (never fall back to a source project interpreter)
$pyVersionOutput = & python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[verify] FAIL: python not found on PATH" -ForegroundColor Red
    exit 1
}
Write-Host "[verify] $pyVersionOutput"
$versionMatch = [regex]::Match($pyVersionOutput, 'Python\s+(\d+)\.(\d+)')
if (-not $versionMatch.Success) {
    Write-Host "[verify] FAIL: cannot parse python version" -ForegroundColor Red
    exit 1
}
$major = [int]$versionMatch.Groups[1].Value
$minor = [int]$versionMatch.Groups[2].Value
if (($major -lt 3) -or ($major -eq 3 -and $minor -lt 11)) {
    Write-Host "[verify] FAIL: python 3.11+ required, found $major.$minor" -ForegroundColor Red
    exit 1
}

$script:failures = @()

function Run-Check {
    param([string]$Name, [scriptblock]$Body)
    Write-Host ""
    Write-Host "[verify] === $Name ==="
    & $Body
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[verify] FAIL: $Name" -ForegroundColor Red
        $script:failures += $Name
    }
    else {
        Write-Host "[verify] PASS: $Name" -ForegroundColor Green
    }
}

Run-Check "pytest smoke" { python -m pytest tests/smoke -q }
Run-Check "ruff check" { python -m ruff check . }
Run-Check "mypy src" { python -m mypy src }
Run-Check "import ai_scientist_mvp" { python -c "import sys; sys.path.insert(0, 'src'); import ai_scientist_mvp" }

Write-Host ""
if ($script:failures.Count -eq 0) {
    Write-Host "[verify] ALL CHECKS PASSED" -ForegroundColor Green
    exit 0
}
Write-Host ("[verify] {0} CHECK(S) FAILED: {1}" -f $script:failures.Count, ($script:failures -join ", ")) -ForegroundColor Red
exit 1
