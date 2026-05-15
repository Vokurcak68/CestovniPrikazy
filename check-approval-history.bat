@echo off
set PGPASSWORD=166f3a5cceec4ef49cadc3ab79c7591aA!7k
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U travel_orders_app -d travel_orders -f "C:\CestovniPrikazy\database\check-approval-history.sql"
pause
