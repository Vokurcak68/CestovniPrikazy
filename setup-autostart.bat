@echo off
echo Nastavuji automaticke spousteni backendu...

REM Create scheduled task to run backend at startup
schtasks /create /tn "CestovniPrikazyBackend" /tr "C:\CestovniPrikazy\start-backend-service.bat" /sc onlogon /rl highest /f

if %errorlevel% equ 0 (
    echo.
    echo Uspech! Backend se nyni bude spoustet automaticky pri prihlaseni.
    echo.
    echo Pro test spusteni pouzij:
    echo   schtasks /run /tn "CestovniPrikazyBackend"
    echo.
    echo Pro zastaveni pouzij:
    echo   taskkill /F /IM python.exe /FI "WINDOWTITLE eq *Flask*"
    echo.
    echo Pro odstraneni automatickeho spousteni pouzij:
    echo   schtasks /delete /tn "CestovniPrikazyBackend" /f
) else (
    echo.
    echo CHYBA: Nelze vytvorit naplanovany ukol.
    echo Spust tento skript jako administrator.
)

pause
