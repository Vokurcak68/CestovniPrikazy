# Registrace automatickeho spusteni backendu v Task Scheduleru
# Spust jako spravce (pravym tlacitkem -> Spustit jako spravce)

$taskName = "CestovniPrikazyBackend"

# Odstrann stary task pokud existuje
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\CestovniPrikazy\start-backend-autostart.ps1"

$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $taskName `
    -TaskPath "\" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Automaticke spusteni backendu Cestovni prikazy pri startu Windows" `
    -Force

if ($?) {
    Write-Host ""
    Write-Host "OK: Task '$taskName' zaregistrovan." -ForegroundColor Green
    Write-Host "Backend se bude spoustet automaticky pri kazdem startu Windows."
    Write-Host ""
    Write-Host "Pro okamzite spusteni tasku:"
    Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
    Write-Host ""
    Write-Host "Pro odstraneni tasku:"
    Write-Host "  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
} else {
    Write-Host "CHYBA: Registrace selhala." -ForegroundColor Red
}

Read-Host "Stiskni Enter pro zavreni"
