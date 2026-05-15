#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check import errors in MSSQL"""

import pyodbc

# Use Windows authentication
conn_str = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=192.168.0.54;"
    "DATABASE=Helios002;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;Encrypt=yes;"
)

# Connect and query
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

cursor.execute("""
    SELECT TOP 5
        ImportId,
        CisloCestovnihoPrikazu,
        ExportStatus,
        HeliosCestakId,
        ImportFinishedAt,
        ImportError
    FROM dbo.vok_CPImportCestaky
    ORDER BY ImportFinishedAt DESC
""")

print("Recent imports:")
print("-" * 150)
for row in cursor.fetchall():
    print(f"ImportId: {row.ImportId}")
    print(f"  Order: {row.CisloCestovnihoPrikazu}")
    print(f"  Status: {row.ExportStatus}")
    print(f"  Helios ID: {row.HeliosCestakId}")
    print(f"  Finished: {row.ImportFinishedAt}")
    print(f"  Error: {row.ImportError or '(none)'}")
    print()

cursor.close()
conn.close()
