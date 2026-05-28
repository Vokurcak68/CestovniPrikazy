# Spusteni backendu CestovniPrikazy pri startu systemu
# Tento skript spousti Task Scheduler - nespoustej rucne

$ROOT = "C:\CestovniPrikazy"
$PYTHON = "$ROOT\.venv\Scripts\python.exe"
$APP = "$ROOT\travel-orders-server\app.py"
$LOG = "$ROOT\backend.log"
$ENV_FILE = "$ROOT\.env"

# Nacti promenne prostredi z .env
if (Test-Path $ENV_FILE) {
    Get-Content $ENV_FILE | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
        $parts = $_ -split '=', 2
        if ($parts.Count -eq 2) {
            $name = $parts[0].Trim().TrimStart([char]0xFEFF)
            $value = $parts[1].Trim()
            [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}

# Spust backend s logovanim
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $LOG -Value "`n[$timestamp] Backend spusten autostartem (Task Scheduler)"

Set-Location "$ROOT\travel-orders-server"
& $PYTHON $APP >> $LOG 2>&1
