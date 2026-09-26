<#
.SYNOPSIS
Phase 16: one-time Postgres data directory bootstrap for a packaged install, called from
NSIS_HOOK_POSTINSTALL (see hooks.nsi) after generate_first_run_config.ps1 has already
written C:\ProgramData\Vero.ai\config.env (this script reads the vero role's password
back out of it, so both scripts agree on the same credentials).

Idempotent: does nothing if the data directory already exists (a reinstall/upgrade, not
a first install) - initdb refuses to run against a non-empty directory anyway, but this
avoids even trying and printing a confusing error on every upgrade.

Bootstraps with initdb (trust auth, loopback only for this one-off setup step), starts
postgres.exe briefly under pg_ctl to create the `vero` role + database with the real
generated password, then stops it again - the NSSM service registration (register_
services.ps1) is what actually keeps it running afterward, not this script.
#>
param(
    [Parameter(Mandatory = $true)][string]$PostgresBinDir  # .../packaging/postgres/bin, bundled as an installer resource
)

$ErrorActionPreference = "Stop"

$ConfigPath = "C:\ProgramData\Vero.ai\config.env"
$PgDataDir = "C:\ProgramData\Vero.ai\pgdata"

if (Test-Path $PgDataDir) {
    Write-Host "$PgDataDir already exists - skipping initdb (reinstall/upgrade)."
    exit 0
}

if (-not (Test-Path $ConfigPath)) {
    throw "$ConfigPath does not exist - run generate_first_run_config.ps1 first."
}

$config = @{}
Get-Content $ConfigPath | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object {
    $key, $value = $_ -split '=', 2
    $config[$key] = $value
}
$postgresPassword = $config["VERO_POSTGRES_PASSWORD"]
if (-not $postgresPassword) { throw "VERO_POSTGRES_PASSWORD missing from $ConfigPath" }
$postgresPort = $config["VERO_POSTGRES_PORT"]
if (-not $postgresPort) { throw "VERO_POSTGRES_PORT missing from $ConfigPath" }

$InitdbExe = Join-Path $PostgresBinDir "initdb.exe"
$PgCtlExe = Join-Path $PostgresBinDir "pg_ctl.exe"
$PsqlExe = Join-Path $PostgresBinDir "psql.exe"

Write-Host "Running initdb into $PgDataDir ..."
& $InitdbExe -D $PgDataDir -U postgres --auth=trust --locale=en-US --encoding=UTF8
if ($LASTEXITCODE -ne 0) { throw "initdb failed" }

# --auth=trust + listening on 127.0.0.1 only, for this one-off bootstrap step alone -
# the real service (registered separately) still starts with the same data directory,
# whose pg_hba.conf this leaves as initdb's own default (loopback-only, password auth
# for non-superuser roles), not exposed to the network at any point. Same port
# generate_first_run_config.ps1 already probed as free and put in DATABASE_URL - using
# any other port here would bootstrap correctly but leave the backend unable to connect.
Write-Host "Starting postgres temporarily on port $postgresPort to create the vero role and database ..."
& $PgCtlExe -D $PgDataDir -l "C:\ProgramData\Vero.ai\pg_bootstrap.log" -o "-h 127.0.0.1 -p $postgresPort" start
if ($LASTEXITCODE -ne 0) { throw "pg_ctl start failed - see C:\ProgramData\Vero.ai\pg_bootstrap.log" }

try {
    # Two separate psql invocations, not one combined string: CREATE DATABASE cannot run
    # inside a transaction block, and psql -c with multiple ;-separated statements wraps
    # them all in one implicit transaction - confirmed by this failing for real on the
    # first attempt ("ERROR: CREATE DATABASE cannot run inside a transaction block").
    $escapedPassword = $postgresPassword.Replace("'", "''")
    & $PsqlExe -h 127.0.0.1 -p $postgresPort -U postgres -d postgres -c "CREATE ROLE vero LOGIN PASSWORD '$escapedPassword';"
    if ($LASTEXITCODE -ne 0) { throw "role creation failed" }
    & $PsqlExe -h 127.0.0.1 -p $postgresPort -U postgres -d postgres -c "CREATE DATABASE vero OWNER vero;"
    if ($LASTEXITCODE -ne 0) { throw "database creation failed" }
    Write-Host "Created the vero role and database."
} finally {
    # pg_ctl stop reads the port back out of postmaster.pid in the data directory - no
    # -o flag needed here (that's a start-only option, passed through to postgres itself).
    & $PgCtlExe -D $PgDataDir stop
}
