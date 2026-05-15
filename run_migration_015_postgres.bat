@echo off
echo Zadej heslo pro PostgreSQL uzivatele postgres:
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -d travel_orders -f "C:\CestovniPrikazy\database\migrations\015_travel_requests_and_multistage_approval.sql"
pause
