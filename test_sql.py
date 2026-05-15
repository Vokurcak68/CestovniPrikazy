import sys
import os

# Add server path
sys.path.insert(0, r'C:\CestovniPrikazy\travel-orders-server')
os.chdir(r'C:\CestovniPrikazy\travel-orders-server')

# Set environment
os.environ['TRAVEL_DB_PASSWORD'] = ''

from app import run_psql_json

# Test simple query with accountant_submit parameter
test_sql = """
SELECT
  CASE WHEN :'accountant_submit'::boolean THEN 'TRUE' ELSE 'FALSE' END AS result;
"""

try:
    result = run_psql_json(test_sql, {"accountant_submit": False})
    print("Test 1 (False):", result)
except Exception as e:
    print("Error 1:", e)

try:
    result = run_psql_json(test_sql, {"accountant_submit": True})
    print("Test 2 (True):", result)
except Exception as e:
    print("Error 2:", e)
