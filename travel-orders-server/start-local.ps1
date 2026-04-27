$ErrorActionPreference = "Stop"

$env:TRAVEL_DB_HOST = if ($env:TRAVEL_DB_HOST) { $env:TRAVEL_DB_HOST } else { "localhost" }
$env:TRAVEL_DB_PORT = if ($env:TRAVEL_DB_PORT) { $env:TRAVEL_DB_PORT } else { "5432" }
$env:TRAVEL_DB_NAME = if ($env:TRAVEL_DB_NAME) { $env:TRAVEL_DB_NAME } else { "travel_orders" }
$env:TRAVEL_DB_USER = if ($env:TRAVEL_DB_USER) { $env:TRAVEL_DB_USER } else { "postgres" }
$env:TRAVEL_PSQL = if ($env:TRAVEL_PSQL) { $env:TRAVEL_PSQL } else { "C:\Program Files\PostgreSQL\18\bin\psql.exe" }

if (-not $env:TRAVEL_DB_PASSWORD) {
  $secure = Read-Host "PostgreSQL password" -AsSecureString
  $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    $env:TRAVEL_DB_PASSWORD = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  } finally {
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
}

python "$PSScriptRoot\app.py"
