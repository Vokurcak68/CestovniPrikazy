@echo off
echo Spoustim synchronizaci do MSSQL...
cd /d C:\CestovniPrikazy\tools
call ..\.venv\Scripts\activate.bat
python sync_helios_import_queue.py --skip-schema
pause
