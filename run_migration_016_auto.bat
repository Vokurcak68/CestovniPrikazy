@echo off
set PGPASSWORD=AdminO225588
"C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -U postgres -d travel_orders -f "C:\CestovniPrikazy\database\migrations\016_add_transport_to_travel_request.sql"
