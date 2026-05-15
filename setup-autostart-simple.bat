@echo off
echo Nastavuji automaticke spousteni backendu pomoci Autostart slozky...

REM Get the Startup folder path
set STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

REM Create shortcut to start-backend-service.bat in Startup folder
echo Set oWS = WScript.CreateObject("WScript.Shell") > CreateShortcut.vbs
echo sLinkFile = "%STARTUP_FOLDER%\CestovniPrikazyBackend.lnk" >> CreateShortcut.vbs
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> CreateShortcut.vbs
echo oLink.TargetPath = "C:\CestovniPrikazy\start-backend-service.bat" >> CreateShortcut.vbs
echo oLink.WorkingDirectory = "C:\CestovniPrikazy" >> CreateShortcut.vbs
echo oLink.Description = "Cestovni Prikazy Backend" >> CreateShortcut.vbs
echo oLink.WindowStyle = 7 >> CreateShortcut.vbs
echo oLink.Save >> CreateShortcut.vbs

cscript //nologo CreateShortcut.vbs
del CreateShortcut.vbs

if exist "%STARTUP_FOLDER%\CestovniPrikazyBackend.lnk" (
    echo.
    echo Uspech! Backend se nyni bude spoustet automaticky pri prihlaseni.
    echo.
    echo Zkratka byla vytvorena v: %STARTUP_FOLDER%
    echo.
    echo Pro okamzite spusteni backendu pouzij:
    echo   C:\CestovniPrikazy\start-backend-service.bat
    echo.
    echo Pro odstraneni automatickeho spousteni smaz soubor:
    echo   %STARTUP_FOLDER%\CestovniPrikazyBackend.lnk
) else (
    echo.
    echo CHYBA: Nelze vytvorit zkratku.
)

echo.
pause
