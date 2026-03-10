param(
    [ValidateSet("local", "production")]
    [string]$Overlay = "local",
    [string]$EnvPath = ".env",
    [string]$PublicBackendUrl,
    [string]$CorsOrigins,
    [string]$PrometheusPublicUrl = "",
    [string]$GrafanaPublicUrl = ""
)

$ErrorActionPreference = "Stop"

function Read-EnvFile {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Env file not found: $Path"
    }

    $values = @{}
    foreach ($line in Get-Content $Path) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) {
            continue
        }

        $parts = $line.Split("=", 2)
        if ($parts.Count -eq 2) {
            $values[$parts[0].Trim()] = $parts[1]
        }
    }

    return $values
}

function Get-RequiredValue {
    param(
        [hashtable]$Values,
        [string]$Key
    )

    $value = $Values[$Key]
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Missing required value '$Key' in $EnvPath"
    }

    return $value
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$fullEnvPath = if ([System.IO.Path]::IsPathRooted($EnvPath)) { $EnvPath } else { Join-Path $projectRoot $EnvPath }
$overlayRoot = Join-Path $projectRoot "k8s\overlays\$Overlay"
$configPath = Join-Path $overlayRoot "config.env"
$secretPath = Join-Path $overlayRoot "secrets.env"

$values = Read-EnvFile -Path $fullEnvPath

$postgresDb = Get-RequiredValue -Values $values -Key "POSTGRES_DB"
$postgresUser = Get-RequiredValue -Values $values -Key "POSTGRES_USER"
$postgresPassword = Get-RequiredValue -Values $values -Key "POSTGRES_PASSWORD"
$secretKey = Get-RequiredValue -Values $values -Key "SECRET_KEY"

if ([string]::IsNullOrWhiteSpace($PublicBackendUrl)) {
    if ($Overlay -eq "local") {
        $PublicBackendUrl = "http://smart-auth.localtest.me"
    }
    else {
        throw "PublicBackendUrl is required for the production overlay"
    }
}

if ([string]::IsNullOrWhiteSpace($CorsOrigins)) {
    $CorsOrigins = $PublicBackendUrl
}

$databaseUrl = "postgresql+asyncpg://${postgresUser}:${postgresPassword}@postgres:5432/${postgresDb}"
$appEnv = if ($Overlay -eq "local") { "development" } else { "production" }
$debugValue = if ($Overlay -eq "local") { "true" } else { "false" }

$configLines = @(
    "APP_NAME=$($values['APP_NAME'])",
    "APP_ENV=$appEnv",
    "DEBUG=$debugValue",
    "API_V1_PREFIX=$($values['API_V1_PREFIX'])",
    "LOG_LEVEL=$($values['LOG_LEVEL'])",
    "ACCESS_TOKEN_EXPIRE_MINUTES=$($values['ACCESS_TOKEN_EXPIRE_MINUTES'])",
    "REFRESH_TOKEN_EXPIRE_DAYS=$($values['REFRESH_TOKEN_EXPIRE_DAYS'])",
    "POSTGRES_DB=$postgresDb",
    "POSTGRES_USER=$postgresUser",
    "REDIS_URL=redis://redis:6379/0",
    "PUBLIC_BACKEND_URL=$PublicBackendUrl",
    "CORS_ORIGINS=$CorsOrigins",
    "PROMETHEUS_PUBLIC_URL=$PrometheusPublicUrl",
    "GRAFANA_PUBLIC_URL=$GrafanaPublicUrl",
    "RATE_LIMIT_AUTH_REQUESTS=$($values['RATE_LIMIT_AUTH_REQUESTS'])",
    "RATE_LIMIT_AUTH_WINDOW_SECONDS=$($values['RATE_LIMIT_AUTH_WINDOW_SECONDS'])",
    "RATE_LIMIT_FAIL_CLOSED=$($values['RATE_LIMIT_FAIL_CLOSED'])",
    "TRUST_PROXY_HEADERS=$($values['TRUST_PROXY_HEADERS'])",
    "TRUSTED_PROXY_CIDRS=$($values['TRUSTED_PROXY_CIDRS'])"
)

$secretLines = @(
    "SECRET_KEY=$secretKey",
    "POSTGRES_PASSWORD=$postgresPassword",
    "DATABASE_URL=$databaseUrl",
    "GOOGLE_CLIENT_ID=$($values['GOOGLE_CLIENT_ID'])",
    "GOOGLE_CLIENT_SECRET=$($values['GOOGLE_CLIENT_SECRET'])",
    "GITHUB_CLIENT_ID=$($values['GITHUB_CLIENT_ID'])",
    "GITHUB_CLIENT_SECRET=$($values['GITHUB_CLIENT_SECRET'])"
)

Set-Content -Path $configPath -Value ($configLines -join [Environment]::NewLine)
Set-Content -Path $secretPath -Value ($secretLines -join [Environment]::NewLine)

Write-Host "Wrote $configPath" -ForegroundColor Green
Write-Host "Wrote $secretPath" -ForegroundColor Green