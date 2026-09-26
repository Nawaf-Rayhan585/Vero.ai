<#
.SYNOPSIS
Phase 16: stops and removes "VeroAiBackend"/"VeroAiPostgres", called from
NSIS_HOOK_PREUNINSTALL. Deliberately does not touch C:\ProgramData\Vero.ai\{pgdata,
config.env,*.log} - those are left behind on uninstall by design (see docs/ROADMAP.md's
Phase 16 entry), so a reinstall picks up existing camera/event history untouched.
#>
param(
    [Parameter(Mandatory = $true)][string]$NssmExe
)

$ErrorActionPreference = "SilentlyContinue"  # an uninstall must not get stuck on a service that's already gone

foreach ($name in @("VeroAiBackend", "VeroAiPostgres")) {
    $service = Get-Service -Name $name -ErrorAction SilentlyContinue
    if ($service) {
        Write-Host "Stopping $name ..."
        Stop-Service -Name $name -Force -ErrorAction SilentlyContinue
        Write-Host "Removing $name ..."
        & $NssmExe remove $name confirm
    } else {
        Write-Host "$name was not registered - nothing to remove."
    }
}
