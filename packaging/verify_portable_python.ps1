<#
.SYNOPSIS
Phase 16: proves a venv built by build_portable_python.ps1 is genuinely relocatable -
copies it to a scratch directory *other than* where it was built, then runs it from
there. A venv with a leaked absolute path (pyvenv.cfg, a launcher stub) fails this in a
way that "the files exist and pip install succeeded" never would have caught.

Usage:
    powershell -File packaging/verify_portable_python.ps1 -VenvDir packaging/dist/pyruntime
#>
param(
    [Parameter(Mandatory = $true)][string]$VenvDir
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $VenvDir)) { throw "$VenvDir does not exist" }

$ScratchDir = Join-Path $env:TEMP ("vero-portable-python-verify-" + [guid]::NewGuid().ToString("N"))
Write-Host "Copying $VenvDir to $ScratchDir (a directory the venv was NOT built in) ..."
Copy-Item -Recurse -Path $VenvDir -Destination $ScratchDir

$PyExe = Join-Path $ScratchDir "Scripts\python.exe"
Write-Host "Running the relocated interpreter's own sanity check ..."
& $PyExe -c "import sys; print('relocated interpreter OK:', sys.executable)"
$interpreterOk = $LASTEXITCODE -eq 0

Write-Host "Checking for uvicorn (fails cleanly if requirements.txt was never installed into this venv) ..."
& $PyExe -m uvicorn --version
$uvicornOk = $LASTEXITCODE -eq 0

Remove-Item -Recurse -Force $ScratchDir

if ($interpreterOk -and $uvicornOk) {
    Write-Host "PASS: the venv at $VenvDir is genuinely relocatable."
    exit 0
} else {
    Write-Host "FAIL: relocated venv did not run cleanly - do not ship this build." -ForegroundColor Red
    exit 1
}
