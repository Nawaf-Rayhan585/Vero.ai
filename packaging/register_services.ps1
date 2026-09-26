<#
.SYNOPSIS
Phase 16: registers "VeroAiPostgres" and "VeroAiBackend" as real Windows Services via
NSSM, called from NSIS_HOOK_POSTINSTALL after init_postgres.ps1 has bootstrapped the
data directory. Both Automatic startup (survive reboot). Phase 17: each runs under its
own least-privilege virtual service account (NT SERVICE\<name>), not the LocalSystem
default - see the ObjectName/icacls block below.

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

# Phase 17: least-privilege virtual service accounts instead of the LocalSystem default -
# no password to manage, "Log on as a service" is granted automatically for these (the
# modern, correct choice for a single, non-domain-joined machine - researched, not
# assumed). Each account is granted rights on the whole C:\ProgramData\Vero.ai tree
# (not surgically scoped to just its own subfolder/log file) - simpler to get right
# without a live service to test the exact ACL boundary against (that test is part of
# the still-deferred real-install step - see docs/ROADMAP.md), and still a large
# reduction from LocalSystem's effectively unrestricted machine-wide access.
foreach ($name in @("VeroAiPostgres", "VeroAiBackend")) {
    & $NssmExe set $name ObjectName "NT SERVICE\$name"
    & icacls "C:\ProgramData\Vero.ai" /grant "NT SERVICE\${name}:(OI)(CI)F" | Out-Null
}

# OPENCV_LOG_LEVEL=SILENT: found by direct testing (Phase 17) that this specific env var
# is the only thing that actually suppresses an OpenCV/FFmpeg-internal warning that can
# print a camera's stream URL - including its embedded credentials - to the console/log on
# a failed connection. app/camera_testing.py's own cv2.setLogLevel(0) call does NOT
# suppress this particular warning (confirmed - it's a different, env-var-only code path),
# so this must be set on the process before it starts, same as VERO_CONFIG_PATH.
& $NssmExe set VeroAiBackend AppEnvironmentExtra "VERO_CONFIG_PATH=$ConfigPath" "OPENCV_LOG_LEVEL=SILENT"
# The backend's own migrations/startup expect Postgres already accepting connections -
# NSSM has no first-class "depends on another NSSM service" concept, so this uses
# Windows's own native service dependency mechanism instead (sc.exe config).
& sc.exe config VeroAiBackend depend= VeroAiPostgres | Out-Null

Write-Host "Starting VeroAiPostgres ..."
Start-Service -Name VeroAiPostgres
Write-Host "Starting VeroAiBackend ..."
Start-Service -Name VeroAiBackend
