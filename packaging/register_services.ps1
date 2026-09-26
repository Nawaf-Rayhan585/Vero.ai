<#
.SYNOPSIS
Phase 16: registers "VeroAiPostgres" and "VeroAiBackend" as real Windows Services via
NSSM, called from NSIS_HOOK_POSTINSTALL after init_postgres.ps1 has bootstrapped the
data directory. Both Automatic startup (survive reboot), LocalSystem (matches Postgres's
own default Windows install behavior; a least-privilege dedicated service account is
noted as an open item for Phase 17 to tighten).

Re-running this against an already-registered service is safe: `nssm install` on an
existing service name fails harmlessly (checked, not assumed) rather than corrupting it,
which is what an upgrade re-install triggers.
#>
param(
    [Parameter(Mandatory = $true)][string]$NssmExe,
    [Parameter(Mandatory = $true)][string]$PostgresBinDir,
    [Parameter(Mandatory = $true)][string]$PythonExe,       # .../pyruntime/Scripts/python.exe
    [Parameter(Mandatory = $true)][string]$BackendDir       # where service_entrypoint.py lives
)

$ErrorActionPreference = "Stop"
$PgDataDir = "C:\ProgramData\Vero.ai\pgdata"
$ConfigPath = "C:\ProgramData\Vero.ai\config.env"

$config = @{}
Get-Content $ConfigPath | Where-Object { $_ -match '^[A-Z_]+=' } | ForEach-Object {
    $key, $value = $_ -split '=', 2
    $config[$key] = $value
}
$postgresPort = $config["VERO_POSTGRES_PORT"]
if (-not $postgresPort) { throw "VERO_POSTGRES_PORT missing from $ConfigPath" }

function Install-OrSkip-Service {
    param([string]$Name, [string]$TargetExe, [string[]]$Arguments, [string]$WorkingDir)

    $existing = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Service '$Name' already registered - leaving it as-is."
        return
    }

    & $NssmExe install $Name $TargetExe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "nssm install $Name failed" }
    & $NssmExe set $Name AppDirectory $WorkingDir
    & $NssmExe set $Name Start SERVICE_AUTO_START
    & $NssmExe set $Name AppStdout "C:\ProgramData\Vero.ai\$Name.log"
    & $NssmExe set $Name AppStderr "C:\ProgramData\Vero.ai\$Name.log"
    Write-Host "Registered service '$Name'."
}

Install-OrSkip-Service -Name "VeroAiPostgres" -TargetExe (Join-Path $PostgresBinDir "postgres.exe") `
    -Arguments @("-D", $PgDataDir, "-p", $postgresPort) -WorkingDir $PostgresBinDir

Install-OrSkip-Service -Name "VeroAiBackend" -TargetExe $PythonExe `
    -Arguments @((Join-Path $BackendDir "service_entrypoint.py")) -WorkingDir $BackendDir

& $NssmExe set VeroAiBackend AppEnvironmentExtra "VERO_CONFIG_PATH=$ConfigPath"
# The backend's own migrations/startup expect Postgres already accepting connections -
# NSSM has no first-class "depends on another NSSM service" concept, so this uses
# Windows's own native service dependency mechanism instead (sc.exe config).
& sc.exe config VeroAiBackend depend= VeroAiPostgres | Out-Null

Write-Host "Starting VeroAiPostgres ..."
Start-Service -Name VeroAiPostgres
Write-Host "Starting VeroAiBackend ..."
Start-Service -Name VeroAiBackend
