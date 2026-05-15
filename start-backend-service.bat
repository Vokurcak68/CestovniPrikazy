@echo off
REM Start backend as a service (no window, log to file)

REM Kill any existing backend process
taskkill /F /IM python.exe /FI "WINDOWTITLE eq CestovniPrikazyBackend*" >nul 2>&1

REM Wait a moment
timeout /t 2 /nobreak >nul

REM Change to backend directory and start
cd /d C:\CestovniPrikazy\travel-orders-server
start /MIN "CestovniPrikazyBackend" cmd /c "C:\CestovniPrikazy\.venv\Scripts\python.exe app.py >> C:\CestovniPrikazy\backend.log 2>&1"

echo Backend started in minimized window. Check backend.log for output.
