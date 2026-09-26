<#
.SYNOPSIS
Phase 16: downloads the third-party binaries the installer bundles (EDB's official
portable PostgreSQL 16 build, NSSM) into gitignored local directories. Not committed to
source control - these are large (~200 MB combined), versioned, third-party build
artifacts, fetched at build time like any other dependency (the same reason
requirements.txt's packages aren't committed to git either), not vendored into history.

Usage (from the repo root):
    powershell -File packaging/fetch_dependencies.ps1
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

$PostgresVersion = "16.15-1"
$PostgresUrl = "https://get.enterprisedb.com/postgresql/postgresql-$PostgresVersion-windows-x64-binaries.zip"
$PostgresDir = Join-Path $RepoRoot "packaging/postgres"

$NssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
$NssmDir = Join-Path $RepoRoot "packaging/nssm"

function Get-AndExtractZip($Url, $DestDir, $Label) {
    if (Test-Path $DestDir) {
        Write-Host "$Label already present at $DestDir - skipping download."
        return
    }
    $tmpZip = Join-Path $env:TEMP ([guid]::NewGuid().ToString("N") + ".zip")
    Write-Host "Downloading $Label from $Url ..."
    Invoke-WebRequest -Uri $Url -OutFile $tmpZip
    $tmpExtract = Join-Path $env:TEMP ([guid]::NewGuid().ToString("N"))
    Expand-Archive -Path $tmpZip -DestinationPath $tmpExtract
    Remove-Item $tmpZip
    return $tmpExtract
}

if (-not (Test-Path $PostgresDir)) {
    $extracted = Get-AndExtractZip -Url $PostgresUrl -DestDir $PostgresDir -Label "PostgreSQL $PostgresVersion"
    # EDB's zip contains a single top-level "pgsql" directory - flatten it so
    # packaging/postgres/bin/... matches what init_postgres.ps1/register_services.ps1
    # expect ($PostgresBinDir = .../postgres/bin).
    Move-Item (Join-Path $extracted "pgsql") $PostgresDir
    Remove-Item -Recurse -Force $extracted
    Write-Host "PostgreSQL binaries ready at $PostgresDir"
}

if (-not (Test-Path $NssmDir)) {
    $extracted = Get-AndExtractZip -Url $NssmUrl -DestDir $NssmDir -Label "NSSM"
    New-Item -ItemType Directory -Force -Path $NssmDir | Out-Null
    # nssm.cc's zip nests win64/win32 subfolders under a version-numbered top directory.
    $nssmExe = Get-ChildItem -Path $extracted -Recurse -Filter "nssm.exe" | Where-Object { $_.FullName -like "*win64*" } | Select-Object -First 1
    Copy-Item $nssmExe.FullName (Join-Path $NssmDir "nssm.exe")
    Remove-Item -Recurse -Force $extracted
    Write-Host "NSSM ready at $NssmDir"
}
