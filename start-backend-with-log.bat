@echo off
REM Start backend with logging

REM Kill any existing backend process
taskkill /F /IM python.exe /FI "COMMANDLINE eq *app.py*" >nul 2>&1

REM Wait a moment
timeout /t 2 /nobreak >nul

REM Start backend in background with output redirect
cd /d C:\CestovniPrikazy\travel-orders-server
start /MIN "CestovniPrikazyBackend" cmd /c "C:\CestovniPrikazy\.venv\Scripts\python.exe app.py >> C:\CestovniPrikazy\backend.log 2>&1"

echo Backend started. Check backend.log for output.
