$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root ".env"

if (Test-Path $envPath) {
    Write-Host ".env already exists: $envPath"
    exit 0
}

function New-RandomSecret {
    param([int]$ByteCount = 32)

    $bytes = New-Object byte[] $ByteCount
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
}

$content = @(
    "LITELLM_MASTER_KEY=sk-$(New-RandomSecret)"
    "LITELLM_SALT_KEY=sk-$(New-RandomSecret)"
    "POSTGRES_PASSWORD=$(New-RandomSecret)"
    "PUBLIC_BASE_URL=http://localhost:3029"
)

[IO.File]::WriteAllLines($envPath, $content)
Write-Host "Created $envPath"
