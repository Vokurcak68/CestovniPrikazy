@echo off
cd /d C:\CestovniPrikazy\travel-orders-server
call venv\Scripts\activate.bat
python ..\fix_status.py
