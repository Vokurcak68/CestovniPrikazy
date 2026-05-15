@echo off
cd /d C:\CestovniPrikazy
C:\CestovniPrikazy\.venv\Scripts\python.exe -c "import psycopg2; conn = psycopg2.connect('host=localhost port=5432 dbname=travel_orders user=travel_orders_app password=166f3a5cceec4ef49cadc3ab79c7591aA!7k'); cur = conn.cursor(); cur.execute(\"SELECT order_no, status, export_status, helios_document_id, helios_exported_at FROM travel.travel_order WHERE order_no = 'CP-2026-0003'\"); row = cur.fetchone(); print(f'Order: {row[0]}'); print(f'Status: {row[1]}'); print(f'Export Status: {row[2]}'); print(f'Helios ID: {row[3]}'); print(f'Exported At: {row[4]}'); cur.close(); conn.close()"
pause
