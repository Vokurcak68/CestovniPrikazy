@echo off
cd /d "C:\CestovniPrikazy"

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Load environment variables from .env
for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    set "%%a=%%b"
)

cd travel-orders-server

REM Override TRAVEL_PSQL path
set TRAVEL_PSQL=C:\Program Files\PostgreSQL\18\bin\psql.exe

echo Starting Flask backend server on port 5055...
python app.py
