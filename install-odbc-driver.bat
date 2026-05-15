@echo off
echo Stahuji Microsoft ODBC Driver 17 for SQL Server...
echo.

REM Download the installer
set INSTALLER_URL=https://go.microsoft.com/fwlink/?linkid=2249006
set INSTALLER_FILE=%TEMP%\msodbcsql_17.msi

echo Stahuju z %INSTALLER_URL%...
curl -L -o "%INSTALLER_FILE%" "%INSTALLER_URL%"

if not exist "%INSTALLER_FILE%" (
    echo CHYBA: Nepodařilo se stáhnout instalátor.
    pause
    exit /b 1
)

echo.
echo Instaluji ODBC Driver 17 for SQL Server...
echo (Toto je standardní Microsoft ovladač a neměl by ovlivnit ostatní aplikace)
echo.

REM Install silently with IACCEPTMSODBCSQLLICENSETERMS=YES
msiexec /i "%INSTALLER_FILE%" /qn IACCEPTMSODBCSQLLICENSETERMS=YES ADDLOCAL=ALL

if %errorlevel% equ 0 (
    echo.
    echo Instalace dokončena úspěšně!
    echo.
) else (
    echo.
    echo CHYBA: Instalace selhala s kódem %errorlevel%
    echo Možná je potřeba spustit tento skript jako administrator.
    echo.
)

REM Clean up
del "%INSTALLER_FILE%"

pause
