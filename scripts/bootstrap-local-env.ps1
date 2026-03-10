param(
    [switch]$Force
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"

if ((Test-Path $envPath) -and -not $Force) {
    Write-Error ".env already exists. Re-run with -Force to replace it."
    exit 1
}

function New-HexSecret([int]$byteCount = 64) {
    $bytes = New-Object byte[] $byteCount
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
}

function New-AlphaNumericSecret([int]$length = 28) {
    $alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".ToCharArray()
    $bytes = New-Object byte[] ($length * 2)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $builder = New-Object System.Text.StringBuilder

    foreach ($byte in $bytes) {
        if ($builder.Length -ge $length) {
            break
        }
        [void]$builder.Append($alphabet[$byte % $alphabet.Length])
    }

    return $builder.ToString()
}

$secretKey = New-HexSecret 64
$postgresPassword = New-AlphaNumericSecret 28
$grafanaPassword = New-AlphaNumericSecret 24

$content = @"
APP_NAME=Smart Auth API
APP_ENV=development
DEBUG=true
API_V1_PREFIX=/api/v1
SECRET_KEY=$secretKey
LOG_LEVEL=INFO
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
POSTGRES_DB=smart_auth
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$postgresPassword
DATABASE_URL=postgresql+asyncpg://postgres:$postgresPassword@db:5432/smart_auth
REDIS_URL=redis://redis:6379/0
PUBLIC_BACKEND_URL=http://localhost
CORS_ORIGINS=http://localhost,http://127.0.0.1
PROMETHEUS_PUBLIC_URL=http://localhost:19090
GRAFANA_PUBLIC_URL=http://localhost:13000
RATE_LIMIT_AUTH_REQUESTS=5
RATE_LIMIT_AUTH_WINDOW_SECONDS=60
RATE_LIMIT_FAIL_CLOSED=true
TRUST_PROXY_HEADERS=false
TRUSTED_PROXY_CIDRS=
PROMETHEUS_PORT=19090
GRAFANA_PORT=13000
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=$grafanaPassword
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
"@

Set-Content -Path $envPath -Value $content -NoNewline
Write-Output "Created secure local .env at $envPath"