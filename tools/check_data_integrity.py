#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path


def load_env_file(root: Path) -> None:
    env_path = root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def run_query(title: str, sql: str) -> int:
    psql = os.environ.get("TRAVEL_PSQL", r"C:\Program Files\PostgreSQL\18\bin\psql.exe")
    host = os.environ.get("TRAVEL_DB_HOST", "localhost")
    port = os.environ.get("TRAVEL_DB_PORT", "5432")
    db = os.environ.get("TRAVEL_DB_NAME", "travel_orders")
    user = os.environ.get("TRAVEL_DB_USER", "postgres")
    pwd = os.environ.get("TRAVEL_DB_PASSWORD", "")
    env = os.environ.copy()
    env["PGPASSWORD"] = pwd

    print(f"\n=== {title} ===")
    cmd = [
        psql,
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-d",
        db,
        "-v",
        "ON_ERROR_STOP=1",
        "-P",
        "pager=off",
        "-c",
        sql,
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
        return result.returncode
    print(result.stdout.strip())
    return 0


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    load_env_file(root)

    queries = [
        (
            "DUPLICITNI CISLA CESTAKU",
            """
            SELECT order_no, COUNT(*) AS cnt
            FROM travel.travel_order
            GROUP BY order_no
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC, order_no;
            """,
        ),
        (
            "ODESLANE/SCHVALENE CESTAKY S PRAZDNOU HLAVICKOU",
            """
            SELECT id, order_no, status, owner_user_id
            FROM travel.travel_order
            WHERE status IN ('submitted','approved')
              AND (COALESCE(TRIM(purpose), '') = '' OR COALESCE(TRIM(destination), '') = '')
            ORDER BY updated_at DESC
            LIMIT 100;
            """,
        ),
        (
            "ODESLANE/SCHVALENE CESTAKY BEZ POLOZEK",
            """
            SELECT o.id, o.order_no, COUNT(l.id) AS line_count
            FROM travel.travel_order o
            LEFT JOIN travel.travel_route_line l ON l.travel_order_id = o.id
            WHERE o.status IN ('submitted','approved')
            GROUP BY o.id, o.order_no
            HAVING COUNT(l.id) = 0
            ORDER BY o.order_no;
            """,
        ),
        (
            "ROZBITA CESTINA V NOTIFIKACICH",
            """
            SELECT
              COUNT(*) FILTER (WHERE title LIKE '%�%') AS replacement_char_rows,
              COUNT(*) AS total_rows
            FROM travel.notification;
            """,
        ),
    ]

    exit_code = 0
    for title, sql in queries:
        code = run_query(title, sql)
        if code != 0:
            exit_code = code
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
