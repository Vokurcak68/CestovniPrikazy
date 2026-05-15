import psycopg2
import json

conn = psycopg2.connect(
    host="localhost",
    database="cestovni_prikazy",
    user="postgres",
    password=""
)
cur = conn.cursor()

# Check current status
print("Current status:")
cur.execute("""
    SELECT o.id::text, o.number, o.status,
           ar.stage::text, ar.status::text as approval_status
    FROM travel.travel_order o
    LEFT JOIN travel.approval_request ar ON ar.travel_order_id = o.id
    WHERE o.number = 'CP-2026-0003'
    ORDER BY ar.created_at DESC;
""")
for row in cur.fetchall():
    print(row)

# Update status to submitted
print("\nUpdating status to 'submitted'...")
cur.execute("""
    UPDATE travel.travel_order
    SET status = 'submitted'
    WHERE number = 'CP-2026-0003'
    RETURNING id::text, number, status;
""")
updated = cur.fetchall()
print("Updated:")
for row in updated:
    print(row)

conn.commit()

# Verify
print("\nVerification:")
cur.execute("""
    SELECT o.id::text, o.number, o.status,
           ar.stage::text, ar.status::text as approval_status
    FROM travel.travel_order o
    LEFT JOIN travel.approval_request ar ON ar.travel_order_id = o.id
    WHERE o.number = 'CP-2026-0003'
    ORDER BY ar.created_at DESC;
""")
for row in cur.fetchall():
    print(row)

cur.close()
conn.close()
print("\nDone!")
