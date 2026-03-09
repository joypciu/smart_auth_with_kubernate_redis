param(
    [switch]$Aggressive,
    [switch]$IncludeNetworks,
    [switch]$ShowBeforeAfter = $true
)

$ErrorActionPreference = "Stop"

function Invoke-DockerCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    Write-Host "`n==> $Label" -ForegroundColor Cyan
    & docker @Arguments
}

if ($ShowBeforeAfter) {
    Invoke-DockerCommand -Arguments @("system", "df") -Label "Docker disk usage before cleanup"
}

Invoke-DockerCommand -Arguments @("container", "prune", "-f") -Label "Removing stopped containers"
Invoke-DockerCommand -Arguments @("image", "prune", "-f") -Label "Removing dangling images"
Invoke-DockerCommand -Arguments @("volume", "prune", "-f") -Label "Removing unused volumes"
Invoke-DockerCommand -Arguments @("builder", "prune", "-f") -Label "Removing old build cache"

if ($IncludeNetworks) {
    Invoke-DockerCommand -Arguments @("network", "prune", "-f") -Label "Removing unused networks"
}

if ($Aggressive) {
    Invoke-DockerCommand -Arguments @("image", "prune", "-a", "-f") -Label "Removing all unused images"
}

if ($ShowBeforeAfter) {
    Invoke-DockerCommand -Arguments @("system", "df") -Label "Docker disk usage after cleanup"
}

Write-Host "`nCleanup complete." -ForegroundColor Green
Write-Host "Running containers were not stopped by this script." -ForegroundColor Yellow
