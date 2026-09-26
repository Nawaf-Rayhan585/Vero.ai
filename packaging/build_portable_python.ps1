<#
.SYNOPSIS
Phase 16: builds a genuinely relocatable Python runtime for the Windows installer to
bundle, so the packaged "VeroAiBackend" service needs zero manual Python/pip steps on a
customer's machine.

Deliberately does NOT copy backend/venv wholesale - a venv created the normal way embeds
absolute paths (pyvenv.cfg's `home = ...`, launcher exe stubs under Scripts/) that would
silently break once moved to Program Files on a different machine. Instead this builds a
brand-new venv with `--copies` (real file copies, not the launcher-stub scheme a normal
venv uses) directly from requirements.txt, so relocatability holds by construction rather
than by patching an existing venv's internals after the fact.

Usage (from the repo root, with a system Python 3.11+ already on PATH):
    powershell -File packaging/build_portable_python.ps1
    powershell -File packaging/build_portable_python.ps1 -OutDir packaging/dist/pyruntime
#>
param(
    [string]$OutDir = "packaging/dist/pyruntime"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RequirementsPath = Join-Path $RepoRoot "backend/requirements.txt"
$FullOutDir = Join-Path $RepoRoot $OutDir

if (Test-Path $FullOutDir) {
    Write-Host "Removing existing $FullOutDir ..."
    Remove-Item -Recurse -Force $FullOutDir
}

Write-Host "Creating a relocatable venv at $FullOutDir ..."
python -m venv --copies $FullOutDir
if ($LASTEXITCODE -ne 0) { throw "python -m venv failed" }

$PyExe = Join-Path $FullOutDir "Scripts\python.exe"

Write-Host "Installing backend/requirements.txt (this pulls Ultralytics/torch/OpenCV/ONNX Runtime - expect several minutes and multiple GB of downloads) ..."
& $PyExe -m pip install --no-cache-dir -r $RequirementsPath
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "Build complete: $FullOutDir"
Write-Host "Verify relocatability before trusting this build - see packaging/verify_portable_python.ps1"
