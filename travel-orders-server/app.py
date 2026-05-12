from __future__ import annotations

import base64
import hashlib
import html
import importlib.util
import json
import os
import re
import secrets
import smtplib
import subprocess
import unicodedata
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from urllib.parse import quote

from flask import Flask, Response, jsonify, request, send_file, send_from_directory


ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "travel-orders-app"
ATTACHMENT_DIR = ROOT / "travel-order-attachments"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())


load_env_file(ROOT / ".env")

PSQL = os.environ.get("TRAVEL_PSQL", r"C:\Program Files\PostgreSQL\18\bin\psql.exe")

DB_HOST = os.environ.get("TRAVEL_DB_HOST", "localhost")
DB_PORT = os.environ.get("TRAVEL_DB_PORT", "5432")
DB_NAME = os.environ.get("TRAVEL_DB_NAME", "travel_orders")
DB_USER = os.environ.get("TRAVEL_DB_USER", "postgres")
DB_PASSWORD = os.environ.get("TRAVEL_DB_PASSWORD")
APP_HOST = os.environ.get("TRAVEL_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("TRAVEL_PORT", "5055"))

SQLCMD = os.environ.get(
    "ERP_SQLCMD",
    r"C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\130\Tools\Binn\SQLCMD.EXE",
)
ERP_DB_SERVER = os.environ.get("ERP_DB_SERVER")
ERP_DB_NAME = os.environ.get("ERP_DB_NAME")
ERP_DB_USER = os.environ.get("ERP_DB_USER")
ERP_DB_PASSWORD = os.environ.get("ERP_DB_PASSWORD")
ERP_DB_ENCRYPT = os.environ.get("ERP_DB_ENCRYPT", "false").lower() in {"1", "true", "yes"}
ERP_USERS_VIEW = os.environ.get("ERP_USERS_VIEW", "hvw_vok_Oresi_CPUzivatele")
ERP_VEHICLES_VIEW = os.environ.get("ERP_VEHICLES_VIEW", "hvw_vok_Oresi_CPAuta")
ERP_EXCHANGE_RATES_VIEW = os.environ.get("ERP_EXCHANGE_RATES_VIEW", "hvw_vok_Oresi_CPKL")
ERP_FOREIGN_COUNTRIES_VIEW = os.environ.get("ERP_FOREIGN_COUNTRIES_VIEW", "hvw_vok_Oresi_CPCestDZ")
ERP_EXPENSE_CODES_VIEW = os.environ.get("ERP_EXPENSE_CODES_VIEW", "hvw_vok_Oresi_CPNaklKod")
HELIOS_IMPORT_API_TOKEN = os.environ.get("HELIOS_IMPORT_API_TOKEN", "")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER or "noreply@localhost")
SMTP_TLS = os.environ.get("SMTP_TLS", "true").lower() in {"1", "true", "yes"}
EMAIL_DEV_MODE = os.environ.get("EMAIL_DEV_MODE", "true").lower() in {"1", "true", "yes"}

TRANSPORT_KINDS = {"private_car", "company_car", "public_transport", "taxi", "plane", "other"}
SEGMENT_TYPES = {"private", "domestic", "foreign"}
FUEL_TYPES = {"ba95", "ba98", "diesel", "electricity", "other"}
DOCUMENT_KINDS = {"receipt", "invoice", "ticket", "other"}
EXPENSE_KINDS = {"fuel", "fare", "lodging", "parking", "meal", "other"}


app = Flask(__name__, static_folder=None)
_HELIOS_SYNC_MODULE = None


class DatabaseError(RuntimeError):
    pass


class ErpError(RuntimeError):
    pass


class HeliosStagingSyncError(RuntimeError):
    pass


def run_psql_json(sql: str, variables: dict[str, object] | None = None):
    if not DB_PASSWORD:
        raise DatabaseError("TRAVEL_DB_PASSWORD is not set.")

    command = [
        PSQL,
        "-h",
        DB_HOST,
        "-p",
        DB_PORT,
        "-U",
        DB_USER,
        "-d",
        DB_NAME,
        "-X",
        "-q",
        "-t",
        "-A",
        "-v",
        "ON_ERROR_STOP=1",
    ]

    rendered_sql = bind_sql(sql, variables or {})
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD
    env["PGCLIENTENCODING"] = "UTF8"

    result = subprocess.run(
        command,
        input=rendered_sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=20,
    )
    if result.returncode != 0:
        raise DatabaseError(result.stderr.strip() or "Database command failed.")

    output = result.stdout.strip()
    if not output:
        return None
    return json.loads(output)


def bind_sql(sql: str, variables: dict[str, object]) -> str:
    rendered = sql
    for key, value in variables.items():
        rendered = rendered.replace(f":'{key}'", sql_literal(value))
    return rendered


def sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def run_sqlcmd_json(sql: str, variables: dict[str, object] | None = None):
    if not all((ERP_DB_SERVER, ERP_DB_NAME, ERP_DB_USER, ERP_DB_PASSWORD)):
        raise ErpError("ERP database connection is not configured.")

    rendered_sql = bind_mssql(sql, variables or {})

    try:
        import pyodbc
        conn_str = (
            "DRIVER={SQL Server};"
            f"SERVER={ERP_DB_SERVER};"
            f"DATABASE={ERP_DB_NAME};"
            f"UID={ERP_DB_USER};"
            f"PWD={ERP_DB_PASSWORD};"
        )
        with pyodbc.connect(conn_str, timeout=15) as conn:
            cursor = conn.cursor()
            cursor.execute("SET TEXTSIZE 2147483647; " + rendered_sql)
            row = cursor.fetchone()
    except Exception as exc:
        raise ErpError(f"ERP pyodbc query failed: {exc}") from exc

    if not row:
        return None
    output = row[0] if len(row) else None
    if not output:
        return None
    return json.loads(str(output))
def load_helios_staging_sync_module():
    global _HELIOS_SYNC_MODULE
    if _HELIOS_SYNC_MODULE is not None:
        return _HELIOS_SYNC_MODULE

    module_path = ROOT / "tools" / "sync_helios_import_queue.py"
    spec = importlib.util.spec_from_file_location("travel_orders_helios_staging_sync", module_path)
    if spec is None or spec.loader is None:
        raise HeliosStagingSyncError("helios_sync_module_not_found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _HELIOS_SYNC_MODULE = module
    return module


def helios_import_payload_from_app(limit: int = 500) -> tuple[str, dict]:
    if not HELIOS_IMPORT_API_TOKEN:
        raise HeliosStagingSyncError("missing_helios_import_api_token")

    headers = {"X-Helios-Import-Token": HELIOS_IMPORT_API_TOKEN}
    with app.test_client() as client:
        list_response = client.get(f"/api/helios/import-candidates?limit={limit}&shape=list", headers=headers)
        if list_response.status_code != 200:
            raise HeliosStagingSyncError(f"import_list_api_failed:{list_response.status_code}")
        full_response = client.get(f"/api/helios/import-candidates?limit={limit}", headers=headers)
        if full_response.status_code != 200:
            raise HeliosStagingSyncError(f"import_full_api_failed:{full_response.status_code}")

        list_data = list_response.get_json(silent=True) or {}
        full_data = full_response.get_json(silent=True) or {}

    if not isinstance(list_data.get("items"), list):
        raise HeliosStagingSyncError("import_list_payload_invalid")
    if not isinstance(full_data.get("items"), list):
        raise HeliosStagingSyncError("import_full_payload_invalid")

    full_by_id = {
        str(item.get("importId") or ""): item
        for item in full_data.get("items") or []
        if isinstance(item, dict)
    }
    for item in list_data.get("items") or []:
        if not isinstance(item, dict):
            continue
        import_id = str(item.get("importId") or "")
        item["payloadJson"] = json.dumps(full_by_id.get(import_id) or item, ensure_ascii=False)

    return json.dumps(list_data, ensure_ascii=False), list_data


def sync_helios_import_staging(trigger: str = "") -> dict:
    sync_module = load_helios_staging_sync_module()
    payload, data = helios_import_payload_from_app()

    with sync_module.pyodbc.connect(sync_module.connection_string(), timeout=15) as connection:
        cursor = connection.cursor()
        result = sync_module.sync_payload(cursor, payload)
        connection.commit()

    return {
        "ok": True,
        "trigger": trigger,
        "apiCount": data.get("count", 0),
        **(result or {}),
    }


def decode_command_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    for encoding in ("utf-8-sig", "cp852", "cp1250", "latin-1"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


def bind_mssql(sql: str, variables: dict[str, object]) -> str:
    rendered = sql
    for key, value in variables.items():
        rendered = rendered.replace(f":'{key}'", mssql_literal(value))
    return rendered


def mssql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    return "N'" + str(value).replace("'", "''") + "'"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_verification_url(token: str) -> str:
    base_url = APP_BASE_URL.strip().rstrip("/") or request.url_root.rstrip("/")
    return f"{base_url}/api/auth/verify-email?token={token}"


def send_verification_email(email: str, display_name: str, verification_url: str) -> bool:
    if not SMTP_HOST:
        return False

    message = EmailMessage()
    message["Subject"] = "Ověření účtu pro Cestovní příkazy"
    message["From"] = SMTP_FROM
    message["To"] = email
    greeting = display_name or email
    message.set_content(
        "\n".join(
            [
                f"Dobrý den, {greeting},",
                "",
                "pro dokončení registrace do aplikace Cestovní příkazy otevřete tento odkaz:",
                verification_url,
                "",
                "Odkaz platí 24 hodin.",
            ]
        )
    )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
        if SMTP_TLS:
            smtp.starttls()
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(message)
    return True


def send_app_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    if not to_email:
        return False, "missing_recipient"
    if not SMTP_HOST:
        return False, "smtp_not_configured"
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            if SMTP_TLS:
                smtp.starttls()
            if SMTP_USER:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
            smtp.send_message(msg)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def get_current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None

    hashed = token_hash(auth.removeprefix("Bearer ").strip())
    sql = """
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT
          u.id::text AS user_id,
          u.login_name::text AS login_name,
          u.email::text AS email,
          u.display_name,
          COALESCE(array_agg(r.code ORDER BY r.code) FILTER (WHERE r.code IS NOT NULL), ARRAY[]::text[]) AS roles
        FROM travel.auth_session s
        JOIN travel.app_user u ON u.id = s.user_id
        LEFT JOIN travel.user_role ur ON ur.user_id = u.id
        LEFT JOIN travel.role r ON r.id = ur.role_id
        WHERE s.token_hash = :'token_hash'
          AND s.revoked_at IS NULL
          AND s.expires_at > now()
          AND u.is_active
        GROUP BY u.id, u.login_name, u.email, u.display_name
      ) t;
    """
    user = run_psql_json(sql, {"token_hash": hashed})
    return user if user else None


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        request.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def has_role(user: dict, role: str) -> bool:
    return role in set(user.get("roles") or [])


def require_role(role: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"error": "unauthorized"}), 401
            if not has_role(user, role):
                return jsonify({"error": "forbidden"}), 403
            request.current_user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_helios_import_access(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-Helios-Import-Token", "").strip()
        if HELIOS_IMPORT_API_TOKEN and secrets.compare_digest(token, HELIOS_IMPORT_API_TOKEN):
            request.current_user = {
                "user_id": "",
                "login_name": "helios-import",
                "email": "",
                "display_name": "Helios import",
                "roles": ["helios_import"],
            }
            return fn(*args, **kwargs)

        user = get_current_user()
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        if not (has_role(user, "admin") or has_role(user, "accountant")):
            return jsonify({"error": "forbidden"}), 403
        request.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def get_helios_access_user(allow_query_token: bool = False):
    token = request.headers.get("X-Helios-Import-Token", "").strip()
    if allow_query_token and not token:
        token = str(request.args.get("token") or "").strip()
    if HELIOS_IMPORT_API_TOKEN and token and secrets.compare_digest(token, HELIOS_IMPORT_API_TOKEN):
        return {
            "user_id": "",
            "login_name": "helios-import",
            "email": "",
            "display_name": "Helios import",
            "roles": ["helios_import"],
        }

    user = get_current_user()
    if user and (has_role(user, "admin") or has_role(user, "accountant")):
        return user
    return None


def require_helios_preview_access(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = get_helios_access_user(allow_query_token=True)
        if not user:
            return Response("NeoprĂˇvnÄ›nĂ˝ pĹ™Ă­stup k nĂˇhledu cestovnĂ­ho pĹ™Ă­kazu.", status=401, mimetype="text/plain")
        request.current_user = user
        return fn(*args, **kwargs)

    return wrapper


@app.errorhandler(DatabaseError)
def database_error(error):
    return jsonify({"error": "database_error", "message": str(error)}), 500


@app.errorhandler(ErpError)
def erp_error(error):
    return jsonify({"error": "erp_error", "message": str(error)}), 502


@app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    login_name = str(payload.get("login", "")).strip()
    password = str(payload.get("password", ""))

    if not login_name or not password:
        return jsonify({"error": "missing_credentials"}), 400

    auth_sql = """
      SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb)::text
      FROM (
        SELECT
          user_id::text AS user_id,
          login_name::text AS login_name,
          email::text AS email,
          display_name,
          roles
        FROM travel.authenticate_local(:'login', :'password')
      ) t;
    """
    users = run_psql_json(auth_sql, {"login": login_name, "password": password})
    if not users:
        return jsonify({"error": "invalid_credentials"}), 401

    user = users[0]
    token = secrets.token_urlsafe(36)
    hashed = token_hash(token)
    session_sql = """
      WITH inserted AS (
        INSERT INTO travel.auth_session(user_id, token_hash, expires_at, user_agent)
        VALUES (:'user_id'::uuid, :'token_hash', now() + interval '12 hours', :'user_agent')
        RETURNING id::text AS session_id, expires_at
      )
      SELECT to_jsonb(inserted)::text
      FROM inserted;
    """
    session = run_psql_json(
        session_sql,
        {
            "user_id": user["user_id"],
            "token_hash": hashed,
            "user_agent": request.headers.get("User-Agent", ""),
        },
    )

    return jsonify({"token": token, "expires_at": session["expires_at"], "user": user})


@app.post("/api/auth/register")
def register():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or "").strip().lower()
    display_name = str(payload.get("display_name") or "").strip()
    password = str(payload.get("password") or "")

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"error": "invalid_email"}), 400
    if len(password) < 8:
        return jsonify({"error": "weak_password"}), 400
    if not display_name:
        return jsonify({"error": "missing_display_name"}), 400

    existing_sql = """
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT id::text, is_active, email_verified_at IS NOT NULL AS email_verified
        FROM travel.app_user
        WHERE login_name = :'email'::citext
           OR email = :'email'::citext
        LIMIT 1
      ) t;
    """
    existing = run_psql_json(existing_sql, {"email": email}) or {}
    if existing:
        return jsonify({"error": "account_exists"}), 409

    token = secrets.token_urlsafe(32)
    hashed = token_hash(token)
    sql = """
      WITH saved_user AS (
        INSERT INTO travel.app_user(login_name, email, display_name, is_active, source_system)
        VALUES (:'email'::citext, :'email'::citext, :'display_name', false, 'local')
        ON CONFLICT (login_name) DO UPDATE
        SET email = EXCLUDED.email,
            display_name = EXCLUDED.display_name,
            is_active = false,
            email_verified_at = NULL,
            updated_at = now()
        RETURNING id
      ),
      saved_password AS (
        INSERT INTO travel.local_auth_identity(user_id, password_hash, password_login_enabled)
        SELECT id, crypt(:'password', gen_salt('bf', 12)), true
        FROM saved_user
        ON CONFLICT (user_id) DO UPDATE
        SET password_hash = EXCLUDED.password_hash,
            password_changed_at = now(),
            password_login_enabled = true,
            failed_attempts = 0,
            locked_until = NULL
        RETURNING user_id
      ),
      role_added AS (
        INSERT INTO travel.user_role(user_id, role_id)
        SELECT (SELECT id FROM saved_user), r.id
        FROM travel.role r
        WHERE r.code = 'employee'
        ON CONFLICT DO NOTHING
        RETURNING user_id
      ),
      invalidated AS (
        UPDATE travel.email_verification_token
        SET used_at = now()
        WHERE user_id = (SELECT id FROM saved_user)
          AND used_at IS NULL
        RETURNING id
      ),
      verification AS (
        INSERT INTO travel.email_verification_token(user_id, token_hash, email, expires_at)
        SELECT id, :'token_hash', :'email'::citext, now() + interval '24 hours'
        FROM saved_user
        RETURNING id
      )
      SELECT jsonb_build_object('user_id', (SELECT id::text FROM saved_user))::text;
    """
    result = run_psql_json(
        sql,
        {
            "email": email,
            "display_name": display_name,
            "password": password,
            "token_hash": hashed,
        },
    )
    verification_url = build_verification_url(token)
    email_warning = ""
    try:
        email_sent = send_verification_email(email, display_name, verification_url)
    except Exception as error:
        email_sent = False
        email_warning = str(error)
    response = {"ok": True, "emailSent": email_sent, "userId": result["user_id"]}
    if not email_sent and EMAIL_DEV_MODE:
        response["devVerificationUrl"] = verification_url
    if email_warning and EMAIL_DEV_MODE:
        response["emailWarning"] = email_warning
    return jsonify(response)


@app.get("/api/auth/verify-email")
def verify_email():
    token = str(request.args.get("token") or "").strip()
    if not token:
        return "ChybĂ­ ovÄ›Ĺ™ovacĂ­ token.", 400
    hashed = token_hash(token)
    sql = """
      WITH selected AS (
        SELECT id, user_id
        FROM travel.email_verification_token
        WHERE token_hash = :'token_hash'
          AND used_at IS NULL
          AND expires_at > now()
        LIMIT 1
      ),
      token_used AS (
        UPDATE travel.email_verification_token
        SET used_at = now()
        WHERE id = (SELECT id FROM selected)
        RETURNING user_id
      ),
      activated AS (
        UPDATE travel.app_user
        SET is_active = true,
            email_verified_at = now(),
            updated_at = now()
        WHERE id = (SELECT user_id FROM token_used)
        RETURNING id
      )
      SELECT jsonb_build_object('verified', EXISTS (SELECT 1 FROM activated))::text;
    """
    result = run_psql_json(sql, {"token_hash": hashed}) or {}
    if not result.get("verified"):
        return "OvÄ›Ĺ™ovacĂ­ odkaz je neplatnĂ˝ nebo vyprĹˇel.", 400
    return """
      <!doctype html>
      <meta charset="utf-8">
      <title>E-mail ovÄ›Ĺ™en</title>
      <body style="font-family:Segoe UI,Arial,sans-serif;padding:32px">
        <h1>E-mail je ovÄ›Ĺ™enĂ˝</h1>
        <p>ĂšÄŤet je aktivnĂ­. MĹŻĹľeĹˇ se pĹ™ihlĂˇsit do aplikace CestovnĂ­ pĹ™Ă­kazy.</p>
        <p><a href="/">PĹ™ejĂ­t do aplikace</a></p>
      </body>
    """


@app.get("/api/auth/me")
@require_auth
def me():
    return jsonify({"user": request.current_user})


@app.get("/api/users/me/defaults")
@require_auth
def my_defaults():
    sql = """
      SELECT jsonb_build_object(
        'employee', jsonb_build_object(
          'organization', COALESCE(ep.organization_name, ''),
          'name', COALESCE(ep.display_name, u.display_name, ''),
          'personalNo', COALESCE(ep.personal_number, ''),
          'address', COALESCE(ep.address, ''),
          'costCenterCode', COALESCE(ep.cost_center_code, ''),
          'costCenterName', COALESCE(ep.cost_center_name, ''),
          'costCenter', COALESCE(NULLIF(trim(concat_ws(' - ', NULLIF(ep.cost_center_code, ''), NULLIF(ep.cost_center_name, ''))), ''), ''),
          'department', COALESCE(ep.department_name, ''),
          'phone', COALESCE(ep.phone, ''),
          'workStart', COALESCE(to_char(ep.work_start, 'HH24:MI'), '08:00'),
          'workEnd', COALESCE(to_char(ep.work_end, 'HH24:MI'), '16:30')
        ),
        'vehicle', jsonb_build_object(
          'id', COALESCE(v.id::text, ''),
          'brand', COALESCE(v.brand, ''),
          'plate', COALESCE(v.plate, ''),
          'engineVolume', COALESCE(v.engine_volume_cc::text, ''),
          'fuelType', COALESCE(v.fuel_type::text, 'ba95'),
          'consumption', COALESCE(v.consumption_l_per_100km, 0),
          'secondaryFuelType', COALESCE(v.secondary_fuel_type::text, ''),
          'secondaryConsumption', COALESCE(v.secondary_consumption_per_100km, 0),
          'heliosId', COALESCE(v.helios_id, ''),
          'sourceSystem', COALESCE(v.source_system::text, 'local'),
          'heliosExportStatus', COALESCE(v.helios_export_status::text, 'not_ready')
        ),
        'vehicles', COALESCE((
          SELECT jsonb_agg(to_jsonb(vehicle_list) ORDER BY vehicle_list.is_default DESC, vehicle_list.brand, vehicle_list.plate)
          FROM (
            SELECT
              vehicle.id::text AS id,
              COALESCE(vehicle.brand, '') AS brand,
              COALESCE(vehicle.plate, '') AS plate,
              COALESCE(vehicle.engine_volume_cc::text, '') AS "engineVolume",
              COALESCE(vehicle.fuel_type::text, 'ba95') AS "fuelType",
              COALESCE(vehicle.consumption_l_per_100km, 0) AS consumption,
              COALESCE(vehicle.secondary_fuel_type::text, '') AS "secondaryFuelType",
              COALESCE(vehicle.secondary_consumption_per_100km, 0) AS "secondaryConsumption",
              COALESCE(vehicle.helios_id, '') AS "heliosId",
              COALESCE(vehicle.source_system::text, 'local') AS "sourceSystem",
              COALESCE(vehicle.helios_export_status::text, 'not_ready') AS "heliosExportStatus",
              vehicle.helios_export_requested_at AS "heliosExportRequestedAt",
              vehicle.helios_exported_at AS "heliosExportedAt",
              vehicle.helios_export_error AS "heliosExportError",
              COALESCE((
                SELECT jsonb_agg(to_jsonb(document_row) ORDER BY document_row."uploadedAt")
                FROM (
                  SELECT
                    document.id::text AS id,
                    document.client_document_id AS "clientDocumentId",
                    document.document_kind AS "documentKind",
                    document.file_name AS "fileName",
                    document.content_type AS "contentType",
                    document.byte_size AS "byteSize",
                    document.sha256,
                    document.uploaded_at AS "uploadedAt"
                  FROM travel.vehicle_document document
                  WHERE document.vehicle_id = vehicle.id
                ) document_row
              ), '[]'::jsonb) AS documents,
              vehicle.is_default,
              vehicle.is_private
            FROM travel.vehicle vehicle
            WHERE vehicle.owner_user_id = u.id
              AND vehicle.is_active
          ) vehicle_list
        ), '[]'::jsonb),
        'route', jsonb_build_object(
          'transport', COALESCE(ep.default_transport_kind::text, 'private_car')
        ),
        'approver', NULL
      )::text
      FROM travel.app_user u
      LEFT JOIN travel.employee_profile ep ON ep.user_id = u.id
      LEFT JOIN LATERAL (
        SELECT vehicle.*
        FROM travel.vehicle vehicle
        WHERE vehicle.owner_user_id = u.id
          AND vehicle.is_active
        ORDER BY (vehicle.id = ep.default_vehicle_id) DESC, vehicle.is_default DESC, vehicle.created_at DESC
        LIMIT 1
      ) v ON true
      LEFT JOIN travel.app_user approver ON approver.id = ep.default_approver_user_id
      WHERE u.id = :'user_id'::uuid;
    """
    defaults = run_psql_json(sql, {"user_id": request.current_user["user_id"]})
    approvers = get_user_approver_options(request.current_user["user_id"])
    defaults["approvers"] = approvers
    defaults["approver"] = next((approver for approver in approvers if approver.get("is_default")), None)
    return jsonify(defaults)


def get_user_approver_options(user_id: str):
    sql = """
      WITH profile AS (
        SELECT id, default_approver_user_id
        FROM travel.employee_profile
        WHERE user_id = :'user_id'::uuid
        LIMIT 1
      ),
      option_count AS (
        SELECT count(*) AS count
        FROM travel.employee_approver_option option
        WHERE option.employee_profile_id = (SELECT id FROM profile)
          AND option.is_active
      )
      SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.is_default DESC, t.name), '[]'::jsonb)::text
      FROM (
        SELECT
          approver.id::text AS id,
          approver.display_name AS name,
          approver.email::text AS email,
          approver.login_name::text AS login,
          COALESCE(option.is_default, false)
            OR approver.id = (SELECT default_approver_user_id FROM profile) AS is_default
        FROM travel.app_user approver
        JOIN travel.user_role ur ON ur.user_id = approver.id
        JOIN travel.role role ON role.id = ur.role_id AND role.code = 'approver'
        LEFT JOIN travel.employee_approver_option option
          ON option.employee_profile_id = (SELECT id FROM profile)
         AND option.approver_user_id = approver.id
         AND option.is_active
        WHERE approver.is_active
          AND approver.id <> :'user_id'::uuid
          AND (
            (SELECT count FROM option_count) = 0
            OR option.id IS NOT NULL
          )
      ) t;
    """
    return run_psql_json(sql, {"user_id": user_id}) or []


def is_approver_available(user_id: str, approver_user_id: str) -> bool:
    return any(approver.get("id") == approver_user_id for approver in get_user_approver_options(user_id))


def resolve_order_approver(user_id: str, requested_approver_user_id: str = "") -> tuple[str, str]:
    if requested_approver_user_id and requested_approver_user_id == user_id:
        return "", "self_approval_not_allowed"

    approvers = get_user_approver_options(user_id)
    if requested_approver_user_id:
        if any(approver.get("id") == requested_approver_user_id for approver in approvers):
            return requested_approver_user_id, ""
        return "", "approver_not_available"

    default_approver = next((approver for approver in approvers if approver.get("is_default")), None)
    if default_approver:
        return default_approver.get("id") or "", ""

    if approvers:
        return approvers[0].get("id") or "", ""

    return "", "missing_approver"


def get_user_profile(user_id: str):
    sql = """
      SELECT jsonb_build_object(
        'id', u.id::text,
        'login_name', u.login_name::text,
        'display_name', u.display_name,
        'email', COALESCE(u.email::text, ''),
        'organization_name', COALESCE(ep.organization_name, ''),
        'personal_number', COALESCE(ep.personal_number, ''),
        'address', COALESCE(ep.address, ''),
        'phone', COALESCE(ep.phone, ''),
        'work_start', COALESCE(to_char(ep.work_start, 'HH24:MI'), '08:00'),
        'work_end', COALESCE(to_char(ep.work_end, 'HH24:MI'), '16:30'),
        'cost_center_code', COALESCE(ep.cost_center_code, ''),
        'cost_center_name', COALESCE(ep.cost_center_name, ''),
        'department_name', COALESCE(ep.department_name, ''),
        'default_transport_kind', COALESCE(ep.default_transport_kind::text, 'private_car'),
        'default_approver_user_id', COALESCE(ep.default_approver_user_id::text, ''),
        'default_approver_name', COALESCE(approver.display_name, ''),
        'vehicles', COALESCE((
          SELECT jsonb_agg(to_jsonb(vehicle_list) ORDER BY vehicle_list.is_default DESC, vehicle_list.brand, vehicle_list.plate)
          FROM (
            SELECT
              vehicle.id::text AS id,
              COALESCE(vehicle.brand, '') AS brand,
              COALESCE(vehicle.plate, '') AS plate,
              COALESCE(vehicle.engine_volume_cc::text, '') AS engine_volume,
              COALESCE(vehicle.fuel_type::text, 'ba95') AS fuel_type,
              COALESCE(vehicle.consumption_l_per_100km, 0) AS consumption,
              COALESCE(vehicle.secondary_fuel_type::text, '') AS secondary_fuel_type,
              COALESCE(vehicle.secondary_consumption_per_100km, 0) AS secondary_consumption,
              COALESCE(vehicle.helios_id, '') AS helios_id,
              COALESCE(vehicle.source_system::text, 'local') AS source_system,
              COALESCE(vehicle.helios_export_status::text, 'not_ready') AS helios_export_status,
              vehicle.helios_export_requested_at,
              vehicle.helios_exported_at,
              vehicle.helios_export_error,
              COALESCE((
                SELECT jsonb_agg(to_jsonb(document_row) ORDER BY document_row."uploadedAt")
                FROM (
                  SELECT
                    document.id::text AS id,
                    document.client_document_id AS "clientDocumentId",
                    document.document_kind AS "documentKind",
                    document.file_name AS "fileName",
                    document.content_type AS "contentType",
                    document.byte_size AS "byteSize",
                    document.sha256,
                    document.uploaded_at AS "uploadedAt"
                  FROM travel.vehicle_document document
                  WHERE document.vehicle_id = vehicle.id
                ) document_row
              ), '[]'::jsonb) AS documents,
              vehicle.is_default,
              vehicle.is_private
            FROM travel.vehicle vehicle
            WHERE vehicle.owner_user_id = u.id
              AND vehicle.is_active
          ) vehicle_list
        ), '[]'::jsonb)
      )::text
      FROM travel.app_user u
      LEFT JOIN travel.employee_profile ep ON ep.user_id = u.id
      LEFT JOIN travel.app_user approver ON approver.id = ep.default_approver_user_id
      WHERE u.id = :'user_id'::uuid;
    """
    profile = run_psql_json(sql, {"user_id": user_id})
    approvers = get_user_approver_options(user_id)
    profile["approver_options"] = approvers
    selected = next((approver for approver in approvers if approver.get("is_default")), None)
    if selected:
        profile["default_approver_user_id"] = selected["id"]
        profile["default_approver_name"] = selected["name"]
    return profile


@app.get("/api/users/me/profile")
@require_auth
def my_profile():
    return jsonify({"profile": get_user_profile(request.current_user["user_id"])})


@app.put("/api/users/me/profile")
@require_auth
def save_my_profile():
    payload = request.get_json(silent=True) or {}
    user_id = request.current_user["user_id"]
    saved = save_profile_payload(user_id, request.current_user, payload)
    if saved.get("error"):
        return jsonify({"error": saved["error"]}), saved.get("status", 400)
    return jsonify({"profile": get_user_profile(user_id)})


def find_personal_number_conflict(personal_number: str, user_id: str = "") -> dict | None:
    if not personal_number:
        return None
    sql = """
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT
          ep.user_id::text AS user_id,
          COALESCE(u.display_name, ep.display_name, '') AS display_name,
          COALESCE(u.email::text, ep.email::text, '') AS email
        FROM travel.employee_profile ep
        LEFT JOIN travel.app_user u ON u.id = ep.user_id
        WHERE ep.personal_number = :'personal_number'
          AND (
            NULLIF(:'user_id', '') IS NULL
            OR ep.user_id IS DISTINCT FROM NULLIF(:'user_id', '')::uuid
          )
        LIMIT 1
      ) t;
    """
    return run_psql_json(sql, {"personal_number": personal_number, "user_id": user_id}) or None


def find_user_identity_conflict(login_name: str, email: str = "", user_id: str = "") -> dict | None:
    sql = """
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT
          u.id::text AS user_id,
          CASE
            WHEN u.login_name = :'login_name'::citext THEN 'login_exists'
            ELSE 'email_exists'
          END AS error
        FROM travel.app_user u
        WHERE (
            NULLIF(:'user_id', '') IS NULL
            OR u.id <> NULLIF(:'user_id', '')::uuid
          )
          AND (
            u.login_name = :'login_name'::citext
            OR (
              NULLIF(:'email', '') IS NOT NULL
              AND (
                u.email = :'email'::citext
                OR u.login_name = :'email'::citext
              )
            )
          )
        ORDER BY CASE WHEN u.login_name = :'login_name'::citext THEN 0 ELSE 1 END
        LIMIT 1
      ) t;
    """
    return run_psql_json(sql, {"login_name": login_name, "email": email, "user_id": user_id}) or None


def save_profile_payload(
    user_id: str,
    current_user: dict,
    payload: dict,
    *,
    source_system: str = "local",
    sync_vehicles: bool = True,
) -> dict:
    display_name = str(payload.get("display_name") or current_user.get("display_name") or "").strip()
    is_helios_sync = source_system == "helios"
    email = str((current_user.get("email") if is_helios_sync else payload.get("email")) or current_user.get("email") or "").strip()
    personal_number = str(payload.get("personal_number") or "").strip()
    default_transport_kind = str(payload.get("default_transport_kind") or "private_car")
    default_approver_user_id = valid_uuid(payload.get("default_approver_user_id"))
    helios_employee_id = str(payload.get("helios_employee_id") or payload.get("heliosEmployeeId") or "").strip()
    helios_payload = payload.get("helios_payload") if isinstance(payload.get("helios_payload"), dict) else None
    if default_transport_kind not in TRANSPORT_KINDS:
        default_transport_kind = "private_car"
    if not display_name:
        return {"error": "missing_display_name", "status": 400}
    if personal_number and find_personal_number_conflict(personal_number, user_id):
        return {"error": "personal_number_exists", "status": 409}

    sql = """
      WITH updated_user AS (
        UPDATE travel.app_user u
        SET display_name = :'display_name',
            email = CASE
              WHEN :'source_system' = 'helios' THEN u.email
              ELSE NULLIF(:'email', '')::citext
            END,
            source_system = CASE
              WHEN :'source_system' = 'helios' THEN 'mixed'::travel.user_source
              WHEN u.source_system = 'helios' THEN 'mixed'::travel.user_source
              ELSE u.source_system
            END,
            helios_employee_id = COALESCE(NULLIF(:'helios_employee_id', ''), u.helios_employee_id),
            helios_personal_number = CASE WHEN :'source_system' = 'helios' THEN :'personal_number' ELSE u.helios_personal_number END,
            last_synced_at = CASE WHEN :'source_system' = 'helios' THEN now() ELSE u.last_synced_at END
        WHERE u.id = :'user_id'::uuid
        RETURNING u.id, u.login_name, u.email, u.display_name
      ),
      saved_profile AS (
        INSERT INTO travel.employee_profile(
          user_id,
          personal_number,
          display_name,
          email,
          address,
          phone,
          organization_name,
          work_start,
          work_end,
          cost_center_code,
          cost_center_name,
          department_name,
          default_transport_kind,
          helios_employee_id,
          helios_payload,
          last_synced_at,
          is_active
        )
        SELECT
          updated_user.id,
          NULLIF(:'personal_number', ''),
          updated_user.display_name,
          updated_user.email,
          NULLIF(:'address', ''),
          NULLIF(:'phone', ''),
          NULLIF(:'organization_name', ''),
          COALESCE(NULLIF(:'work_start', '')::time, '08:00'::time),
          COALESCE(NULLIF(:'work_end', '')::time, '16:30'::time),
          NULLIF(:'cost_center_code', ''),
          NULLIF(:'cost_center_name', ''),
          NULLIF(:'department_name', ''),
          :'default_transport_kind'::travel.transport_kind,
          NULLIF(:'helios_employee_id', ''),
          NULLIF(:'helios_payload', '')::jsonb,
          CASE WHEN :'source_system' = 'helios' THEN now() ELSE NULL END,
          true
        FROM updated_user
        ON CONFLICT (user_id) DO UPDATE
        SET personal_number = EXCLUDED.personal_number,
            display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            address = EXCLUDED.address,
            phone = EXCLUDED.phone,
            organization_name = EXCLUDED.organization_name,
            work_start = EXCLUDED.work_start,
            work_end = EXCLUDED.work_end,
            cost_center_code = EXCLUDED.cost_center_code,
            cost_center_name = EXCLUDED.cost_center_name,
            department_name = EXCLUDED.department_name,
            default_transport_kind = EXCLUDED.default_transport_kind,
            helios_employee_id = COALESCE(EXCLUDED.helios_employee_id, travel.employee_profile.helios_employee_id),
            helios_payload = COALESCE(EXCLUDED.helios_payload, travel.employee_profile.helios_payload),
            last_synced_at = COALESCE(EXCLUDED.last_synced_at, travel.employee_profile.last_synced_at),
            is_active = true
        RETURNING id
      )
      SELECT jsonb_build_object('ok', true, 'profile_id', (SELECT id::text FROM saved_profile))::text;
    """
    run_psql_json(
        sql,
        {
            "user_id": user_id,
            "display_name": display_name,
            "email": email,
            "personal_number": personal_number,
            "address": payload.get("address") or "",
            "phone": payload.get("phone") or "",
            "organization_name": payload.get("organization_name") or "",
            "work_start": payload.get("work_start") or "",
            "work_end": payload.get("work_end") or "",
            "cost_center_code": payload.get("cost_center_code") or "",
            "cost_center_name": payload.get("cost_center_name") or "",
            "department_name": payload.get("department_name") or "",
            "default_transport_kind": default_transport_kind,
            "source_system": "helios" if source_system == "helios" else "local",
            "helios_employee_id": helios_employee_id,
            "helios_payload": json.dumps(helios_payload, ensure_ascii=False) if helios_payload else "",
        },
    )
    if sync_vehicles:
        save_user_vehicles(user_id, normalize_vehicles(payload))
    if default_approver_user_id:
        try:
            save_user_default_approver(user_id, default_approver_user_id)
        except DatabaseError:
            return {"error": "approver_not_available", "status": 400}
    return {"ok": True}


@app.post("/api/users/me/erp-sync")
@require_auth
def sync_my_profile_from_erp():
    payload = request.get_json(silent=True) or {}
    user_id = request.current_user["user_id"]
    personal_number = str(payload.get("personal_number") or "").strip()
    current_profile = None
    if not personal_number:
        current_profile = get_user_profile(user_id)
        personal_number = str(current_profile.get("personal_number") or "").strip()
    if not personal_number:
        return jsonify({"error": "missing_personal_number"}), 400

    employee_row = fetch_erp_employee(personal_number)
    if not employee_row:
        return jsonify({"error": "erp_employee_not_found"}), 404

    vehicle_rows = fetch_erp_vehicles(personal_number)
    if current_profile is None:
        current_profile = get_user_profile(user_id)
    profile_payload = erp_employee_to_profile_payload(
        employee_row,
        personal_number,
        request.current_user,
        current_profile,
    )
    save_result = save_profile_payload(
        user_id,
        request.current_user,
        profile_payload,
        source_system="helios",
        sync_vehicles=False,
    )
    if save_result.get("error"):
        return jsonify({"error": save_result["error"]}), save_result.get("status", 400)

    vehicle_payloads = [
        vehicle
        for vehicle in (
            erp_vehicle_to_payload(row, personal_number, index)
            for index, row in enumerate(vehicle_rows or [])
        )
        if vehicle
    ]
    vehicle_sync = save_erp_vehicles(user_id, vehicle_payloads)
    role_sync = sync_erp_user_roles(user_id, employee_row)

    return jsonify(
        {
            "profile": get_user_profile(user_id),
            "erp": {
                "employeeFound": True,
                "vehicleCount": len(vehicle_payloads),
                "vehicleSync": vehicle_sync,
                "roleSync": role_sync,
            },
        }
    )


@app.get("/api/vehicles/<vehicle_id>/documents/<document_id>")
@require_auth
def download_vehicle_document(vehicle_id, document_id):
    vehicle_uuid = valid_uuid(vehicle_id)
    document_uuid = valid_uuid(document_id)
    if not vehicle_uuid or not document_uuid:
        return jsonify({"error": "not_found"}), 404

    sql = """
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT
          document.file_name AS file_name,
          document.content_type AS content_type,
          document.storage_key AS storage_key
        FROM travel.vehicle_document document
        JOIN travel.vehicle vehicle ON vehicle.id = document.vehicle_id
        WHERE document.id = :'document_id'::uuid
          AND vehicle.id = :'vehicle_id'::uuid
          AND (
            vehicle.owner_user_id = :'user_id'::uuid
            OR EXISTS (
              SELECT 1
              FROM travel.user_role ur
              JOIN travel.role role ON role.id = ur.role_id
              WHERE ur.user_id = :'user_id'::uuid
                AND role.code = 'admin'
            )
          )
        LIMIT 1
      ) t;
    """
    document = run_psql_json(
        sql,
        {
            "vehicle_id": vehicle_uuid,
            "document_id": document_uuid,
            "user_id": request.current_user["user_id"],
        },
    )
    if not document:
        return jsonify({"error": "not_found"}), 404

    target = (ATTACHMENT_DIR / document["storage_key"]).resolve()
    attachment_root = ATTACHMENT_DIR.resolve()
    if attachment_root not in target.parents or not target.exists():
        return jsonify({"error": "not_found"}), 404

    return send_file(
        target,
        mimetype=document.get("content_type") or "application/octet-stream",
        download_name=document.get("file_name") or "OTP",
        as_attachment=False,
    )


@app.post("/api/auth/logout")
@require_auth
def logout():
    auth = request.headers.get("Authorization", "")
    hashed = token_hash(auth.removeprefix("Bearer ").strip())
    sql = """
      WITH updated AS (
        UPDATE travel.auth_session
        SET revoked_at = now()
        WHERE token_hash = :'token_hash'
        RETURNING id
      )
      SELECT jsonb_build_object('ok', true, 'revoked', (SELECT count(*) FROM updated))::text;
    """
    run_psql_json(sql, {"token_hash": hashed})
    return jsonify({"ok": True})


@app.get("/api/approver/dashboard")
@require_auth
def approver_dashboard():
    user_id = request.current_user["user_id"]
    summary_sql = """
      SELECT COALESCE(
        (
          SELECT to_jsonb(t)
          FROM (
            SELECT pending_count, overdue_count, oldest_requested_at, nearest_due_at, pending_gross_amount
            FROM travel.v_approver_dashboard
            WHERE approver_user_id = :'user_id'::uuid
          ) t
        ),
        '{"pending_count":0,"overdue_count":0,"pending_gross_amount":0}'::jsonb
      )::text;
    """
    orders_sql = """
      SELECT COALESCE(jsonb_agg(to_jsonb(t)), '[]'::jsonb)::text
      FROM (
        SELECT
          v.approval_request_id::text,
          v.travel_order_id::text,
          COALESCE(ar.stage::text, 'manager') AS stage,
          v.order_no,
          v.purpose,
          v.destination,
          v.requester_name,
          v.gross_amount,
          v.balance_rounded,
          v.requested_at,
          v.due_at,
          v.is_overdue
        FROM travel.v_approver_pending_orders v
        LEFT JOIN travel.approval_request ar ON ar.id = v.approval_request_id
        WHERE v.approver_user_id = :'user_id'::uuid
        ORDER BY is_overdue DESC, due_at NULLS LAST, requested_at
        LIMIT 50
      ) t;
    """
    return jsonify(
        {
            "summary": run_psql_json(summary_sql, {"user_id": user_id}),
            "orders": run_psql_json(orders_sql, {"user_id": user_id}),
        }
    )


@app.get("/api/travel-orders/my/statuses")
@require_auth
def my_travel_order_statuses():
    sql = """
      SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t."updatedAt" DESC), '[]'::jsonb)::text
      FROM (
        SELECT
          o.id::text AS "travelOrderId",
          o.order_no AS "orderNo",
          o.status::text AS status,
          o.export_status::text AS "exportStatus",
          total.calculation_snapshot AS "calculationSnapshot",
          COALESCE(o.helios_document_id, '') AS "heliosDocumentId",
          o.helios_exported_at AS "heliosExportedAt",
          o.current_approver_user_id::text AS "currentApproverUserId",
          current_approver.display_name AS "currentApproverName",
          o.submitted_at AS "submittedAt",
          o.approved_at AS "approvedAt",
          o.rejected_at AS "rejectedAt",
          o.updated_at AS "updatedAt",
          latest_approval.status::text AS "approvalStatus",
          latest_approval.decided_at AS "approvalDecidedAt",
          latest_approval.decision_comment AS "approvalDecisionComment"
        FROM travel.travel_order o
        LEFT JOIN travel.travel_order_total total ON total.travel_order_id = o.id
        LEFT JOIN travel.app_user current_approver ON current_approver.id = o.current_approver_user_id
        LEFT JOIN LATERAL (
          SELECT ar.status, ar.decided_at, ar.decision_comment
          FROM travel.approval_request ar
          WHERE ar.travel_order_id = o.id
          ORDER BY COALESCE(ar.decided_at, ar.requested_at) DESC
          LIMIT 1
        ) latest_approval ON true
        WHERE o.owner_user_id = :'user_id'::uuid
      ) t;
    """
    return jsonify(run_psql_json(sql, {"user_id": request.current_user["user_id"]}))


@app.post("/api/travel-requests")
@require_auth
def save_travel_request():
    payload = request.get_json(silent=True) or {}
    request_id = valid_uuid(payload.get("id"))
    destination = str(payload.get("destination") or "").strip()
    purpose = str(payload.get("purpose") or "").strip()
    start_at = str(payload.get("startAt") or "").strip()
    end_at = str(payload.get("endAt") or "").strip()
    approver_user_id = valid_uuid(payload.get("approverUserId"))

    if not destination:
        return jsonify({"error": "missing_destination"}), 400
    if not purpose:
        return jsonify({"error": "missing_purpose"}), 400
    if not start_at or not end_at:
        return jsonify({"error": "missing_dates"}), 400
    if not approver_user_id:
        return jsonify({"error": "missing_approver"}), 400
    if approver_user_id == request.current_user["user_id"]:
        return jsonify({"error": "self_approver_not_allowed"}), 400

    request_no = ensure_unique_request_number(str(payload.get("requestNo") or "").strip(), request_id)
    sql = """
      WITH saved AS (
        INSERT INTO travel.travel_request(
          id, request_no, owner_user_id, approver_user_id,
          destination, start_at, end_at, purpose, status
        )
        VALUES (
          COALESCE(NULLIF(:'request_id', '')::uuid, gen_random_uuid()),
          :'request_no',
          :'owner_user_id'::uuid,
          :'approver_user_id'::uuid,
          :'destination',
          :'start_at'::timestamptz,
          :'end_at'::timestamptz,
          :'purpose',
          'draft'
        )
        ON CONFLICT (id) DO UPDATE
        SET approver_user_id = EXCLUDED.approver_user_id,
            destination = EXCLUDED.destination,
            start_at = EXCLUDED.start_at,
            end_at = EXCLUDED.end_at,
            purpose = EXCLUDED.purpose,
            updated_at = now()
        WHERE travel.travel_request.owner_user_id = :'owner_user_id'::uuid
          AND travel.travel_request.status IN ('draft', 'rejected')
        RETURNING id, request_no, status
      )
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT id::text AS id, request_no AS "requestNo", status::text AS status
        FROM saved
      ) t;
    """
    saved = run_psql_json(
        sql,
        {
            "request_id": request_id or "",
            "request_no": request_no,
            "owner_user_id": request.current_user["user_id"],
            "approver_user_id": approver_user_id,
            "destination": destination,
            "start_at": start_at,
            "end_at": end_at,
            "purpose": purpose,
        },
    )
    if not saved or not saved.get("id"):
        return jsonify({"error": "request_save_failed"}), 400
    return jsonify({"request": saved})


@app.post("/api/travel-requests/<travel_request_id>/submit")
@require_auth
def submit_travel_request(travel_request_id):
    request_id = valid_uuid(travel_request_id)
    if not request_id:
        return jsonify({"error": "invalid_request_id"}), 400

    sql = """
      WITH updated AS (
        UPDATE travel.travel_request r
        SET status = 'submitted',
            submitted_at = now(),
            approved_at = NULL,
            rejected_at = NULL,
            rejection_reason = NULL,
            updated_at = now()
        WHERE r.id = :'request_id'::uuid
          AND r.owner_user_id = :'owner_user_id'::uuid
          AND r.status IN ('draft', 'rejected')
        RETURNING r.id, r.request_no, r.approver_user_id, r.destination, r.start_at, r.end_at, r.purpose
      ),
      notify AS (
        INSERT INTO travel.notification(
          recipient_user_id, channel, status, type_code, title, message, object_type, object_id, action_url
        )
        SELECT
          u.approver_user_id,
          'in_app',
          'queued',
          'travel_request_submitted',
          'Nová žádost o vycestování',
          'Žádost ' || u.request_no || ' čeká na schválení.',
          'travel_request',
          u.id,
          '/approvals'
        FROM updated u
        RETURNING id
      )
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT
          u.id::text AS id,
          u.request_no AS "requestNo",
          u.approver_user_id::text AS "approverUserId",
          (SELECT id::text FROM notify LIMIT 1) AS "notificationId"
        FROM updated u
      ) t;
    """
    submitted = run_psql_json(
        sql,
        {"request_id": request_id, "owner_user_id": request.current_user["user_id"]},
    )
    if not submitted or not submitted.get("id"):
        return jsonify({"error": "request_submit_failed"}), 400

    approver = get_user_contact(submitted.get("approverUserId") or "")
    to_email = str(approver.get("email") or "").strip()
    sent = False
    err = ""
    if to_email:
        link = (APP_BASE_URL or request.url_root).rstrip("/") + "/approvals"
        sent, err = send_app_email(
            to_email,
            f"Žádost o vycestování ke schválení: {submitted.get('requestNo')}",
            (
                f"Dobrý den,\n\n"
                f"byla vám přiřazena žádost o vycestování {submitted.get('requestNo')} ke schválení.\n"
                f"Odkaz: {link}\n"
            ),
        )
    submitted["emailSent"] = sent
    if err and EMAIL_DEV_MODE:
        submitted["emailError"] = err
    return jsonify({"submission": submitted})


@app.get("/api/travel-requests/my")
@require_auth
def my_travel_requests():
    sql = """
      SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t."updatedAt" DESC), '[]'::jsonb)::text
      FROM (
        SELECT
          r.id::text AS id,
          r.request_no AS "requestNo",
          r.status::text AS status,
          r.destination AS destination,
          r.start_at AS "startAt",
          r.end_at AS "endAt",
          r.purpose AS purpose,
          r.approver_user_id::text AS "approverUserId",
          a.display_name AS "approverName",
          r.submitted_at AS "submittedAt",
          r.approved_at AS "approvedAt",
          r.rejected_at AS "rejectedAt",
          r.rejection_reason AS "rejectionReason",
          r.updated_at AS "updatedAt"
        FROM travel.travel_request r
        LEFT JOIN travel.app_user a ON a.id = r.approver_user_id
        WHERE r.owner_user_id = :'owner_user_id'::uuid
      ) t;
    """
    return jsonify(run_psql_json(sql, {"owner_user_id": request.current_user["user_id"]}))


@app.get("/api/travel-requests/my/approved-without-order")
@require_auth
def my_approved_requests_without_order():
    sql = """
      SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t."approvedAt" DESC), '[]'::jsonb)::text
      FROM (
        SELECT
          r.id::text AS id,
          r.request_no AS "requestNo",
          r.destination,
          r.start_at AS "startAt",
          r.end_at AS "endAt",
          r.purpose,
          r.approved_at AS "approvedAt"
        FROM travel.travel_request r
        LEFT JOIN travel.travel_order o ON o.travel_request_id = r.id
        WHERE r.owner_user_id = :'owner_user_id'::uuid
          AND r.status = 'approved'
          AND o.id IS NULL
      ) t;
    """
    return jsonify(run_psql_json(sql, {"owner_user_id": request.current_user["user_id"]}))


@app.get("/api/travel-requests/pending")
@require_auth
def pending_travel_requests():
    user_id = request.current_user["user_id"]
    can_review_any = has_role(request.current_user, "admin") or has_role(request.current_user, "accountant")
    sql = """
      SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t."submittedAt" ASC), '[]'::jsonb)::text
      FROM (
        SELECT
          r.id::text AS id,
          r.request_no AS "requestNo",
          r.owner_user_id::text AS "ownerUserId",
          owner.display_name AS "ownerName",
          owner.email::text AS "ownerEmail",
          r.destination,
          r.start_at AS "startAt",
          r.end_at AS "endAt",
          r.purpose,
          r.submitted_at AS "submittedAt"
        FROM travel.travel_request r
        JOIN travel.app_user owner ON owner.id = r.owner_user_id
        WHERE r.status = 'submitted'
          AND (r.approver_user_id = :'user_id'::uuid OR :'can_review_any'::boolean)
      ) t;
    """
    return jsonify(
        run_psql_json(
            sql,
            {
                "user_id": user_id,
                "can_review_any": "true" if can_review_any else "false",
            },
        )
    )


@app.post("/api/travel-requests/<travel_request_id>/decision")
@require_auth
def travel_request_decision(travel_request_id):
    request_id = valid_uuid(travel_request_id)
    if not request_id:
        return jsonify({"error": "invalid_request_id"}), 400

    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if action not in {"approved", "rejected"}:
        return jsonify({"error": "invalid_action"}), 400
    if action == "rejected" and not reason:
        return jsonify({"error": "missing_rejection_reason"}), 400

    user_id = request.current_user["user_id"]
    can_review_any = has_role(request.current_user, "admin")
    sql = """
      WITH decided AS (
        UPDATE travel.travel_request r
        SET status = CASE WHEN :'action' = 'approved' THEN 'approved'::travel.request_status ELSE 'rejected'::travel.request_status END,
            approved_at = CASE WHEN :'action' = 'approved' THEN now() ELSE NULL END,
            rejected_at = CASE WHEN :'action' = 'rejected' THEN now() ELSE NULL END,
            rejection_reason = CASE WHEN :'action' = 'rejected' THEN NULLIF(:'reason', '') ELSE NULL END,
            updated_at = now()
        WHERE r.id = :'request_id'::uuid
          AND r.status = 'submitted'
          AND (r.approver_user_id = :'user_id'::uuid OR :'can_review_any'::boolean)
        RETURNING r.id, r.request_no, r.owner_user_id, r.status, r.rejection_reason
      ),
      notify AS (
        INSERT INTO travel.notification(
          recipient_user_id, channel, status, type_code, title, message, object_type, object_id, action_url
        )
        SELECT
          d.owner_user_id,
          'in_app',
          'queued',
          'travel_request_decided',
          'Rozhodnutí o žádosti o vycestování',
          CASE
            WHEN d.status = 'approved'::travel.request_status THEN 'Žádost ' || d.request_no || ' byla schválena.'
            ELSE 'Žádost ' || d.request_no || ' byla zamítnuta: ' || COALESCE(d.rejection_reason, '')
          END,
          'travel_request',
          d.id,
          '/'
        FROM decided d
        RETURNING id
      )
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT
          d.id::text AS id,
          d.request_no AS "requestNo",
          d.owner_user_id::text AS "ownerUserId",
          d.status::text AS status,
          COALESCE(d.rejection_reason, '') AS "rejectionReason",
          (SELECT id::text FROM notify LIMIT 1) AS "notificationId"
        FROM decided d
      ) t;
    """
    decision = run_psql_json(
        sql,
        {
            "request_id": request_id,
            "action": action,
            "reason": reason,
            "user_id": user_id,
            "can_review_any": "true" if can_review_any else "false",
        },
    )
    if not decision or not decision.get("id"):
        return jsonify({"error": "request_decision_failed"}), 400

    owner = get_user_contact(decision.get("ownerUserId") or "")
    to_email = str(owner.get("email") or "").strip()
    sent = False
    err = ""
    if to_email:
        if decision.get("status") == "approved":
            body = f"Dobrý den,\n\nvaše žádost {decision.get('requestNo')} byla schválena.\n"
        else:
            body = (
                f"Dobrý den,\n\nvaše žádost {decision.get('requestNo')} byla zamítnuta.\n"
                f"Důvod: {decision.get('rejectionReason')}\n"
            )
        sent, err = send_app_email(to_email, f"Rozhodnutí o žádosti: {decision.get('requestNo')}", body)
    decision["emailSent"] = sent
    if err and EMAIL_DEV_MODE:
        decision["emailError"] = err
    return jsonify({"decision": decision})


@app.get("/api/approval-requests/<approval_request_id>/detail")
@require_auth
def approval_request_detail(approval_request_id):
    request_id = valid_uuid(approval_request_id)
    if not request_id:
        return jsonify({"error": "invalid_approval_request"}), 400

    user = request.current_user
    can_review_any = has_role(user, "admin") or has_role(user, "accountant")
    sql = """
      WITH selected AS (
        SELECT ar.*
        FROM travel.approval_request ar
        WHERE ar.id = :'approval_request_id'::uuid
          AND (ar.approver_user_id = :'user_id'::uuid OR :'can_review_any'::boolean)
        LIMIT 1
      ),
      order_row AS (
        SELECT o.*
        FROM travel.travel_order o
        JOIN selected ar ON ar.travel_order_id = o.id
      )
      SELECT to_jsonb(t)::text
      FROM (
        SELECT
          jsonb_build_object(
            'id', selected.id::text,
            'stage', selected.stage::text,
            'status', selected.status,
            'stepNo', selected.step_no,
            'requestedAt', selected.requested_at,
            'dueAt', selected.due_at,
            'decidedAt', selected.decided_at,
            'decisionComment', selected.decision_comment,
            'isOverdue', selected.due_at IS NOT NULL AND selected.due_at < now()
          ) AS approval,
          jsonb_build_object(
            'id', order_row.id::text,
            'number', order_row.order_no,
            'status', order_row.status,
            'purpose', order_row.purpose,
            'destination', order_row.destination,
            'visitedCompanies', order_row.visited_companies,
            'companions', order_row.companions,
            'plannedStartAt', order_row.planned_start_at,
            'plannedEndAt', order_row.planned_end_at,
            'reportDate', order_row.report_date,
            'expectedExpense', order_row.expected_expense,
            'advanceAmount', order_row.advance_amount,
            'submittedAt', order_row.submitted_at,
            'createdAt', order_row.created_at,
            'updatedAt', order_row.updated_at
          ) AS "order",
          jsonb_build_object(
            'id', owner.id::text,
            'name', COALESCE(ep.display_name, owner.display_name),
            'email', COALESCE(ep.email::text, owner.email::text),
            'personalNumber', ep.personal_number,
            'organization', ep.organization_name,
            'department', ep.department_name,
            'costCenter', COALESCE(NULLIF(trim(concat_ws(' - ', NULLIF(ep.cost_center_code, ''), NULLIF(ep.cost_center_name, ''))), ''), ''),
            'address', ep.address,
            'phone', ep.phone,
            'workStart', to_char(ep.work_start, 'HH24:MI'),
            'workEnd', to_char(ep.work_end, 'HH24:MI')
          ) AS employee,
          jsonb_build_object(
            'id', approver.id::text,
            'name', approver.display_name,
            'email', approver.email::text
          ) AS approver,
          COALESCE((
            SELECT to_jsonb(total_row)
            FROM (
              SELECT
                total_km AS "totalKm",
                total_hours AS "totalHours",
                transport_amount AS "transportAmount",
                meal_amount AS "mealAmount",
                lodging_amount AS "lodgingAmount",
                other_amount AS "otherAmount",
                gross_amount AS "grossAmount",
                advance_amount AS "advanceAmount",
                balance_amount AS "balanceAmount",
                balance_rounded AS "balanceRounded",
                calculated_at AS "calculatedAt",
                calculation_snapshot AS "calculationSnapshot"
              FROM travel.travel_order_total
              WHERE travel_order_id = order_row.id
            ) total_row
          ), '{}'::jsonb) AS total,
          COALESCE((
            SELECT jsonb_agg(to_jsonb(line_row) ORDER BY line_row."sequenceNo")
            FROM (
              SELECT
                line.id::text AS id,
                line.sequence_no AS "sequenceNo",
                line.start_at AS "startAt",
                line.from_place AS "from",
                line.to_place AS "to",
                line.end_at AS "endAt",
                line.company_or_place AS company,
                line.purpose,
                line.segment_type::text AS "segmentType",
                line.foreign_country_code AS "countryCode",
                line.foreign_country_name AS "countryName",
                line.foreign_meal_currency AS "foreignCurrencyCode",
                line.foreign_meal_rate AS "foreignMealRate",
                line.foreign_exchange_rate AS "foreignExchangeRate",
                line.foreign_exchange_rate_date AS "foreignExchangeRateDate",
                line.foreign_meal_amount_czk AS "foreignMealAmountCzk",
                line.transport_kind::text AS transport,
                line.km,
                line.fare_amount AS fare,
                line.lodging_amount AS lodging,
                line.other_amount AS other,
                line.free_meals AS "freeMeals",
                line.calculated_hours AS "calculatedHours",
                line.calculated_meal_amount AS "calculatedMealAmount",
                line.calculated_private_vehicle_amount AS "calculatedPrivateVehicleAmount",
                line.calculated_total_amount AS "calculatedTotalAmount",
                line.calculation_detail AS "calculationDetail"
              FROM travel.travel_route_line line
              WHERE line.travel_order_id = order_row.id
              ORDER BY line.sequence_no
            ) line_row
          ), '[]'::jsonb) AS "routeLines",
          COALESCE((
            SELECT jsonb_agg(to_jsonb(attachment_row) ORDER BY attachment_row."uploadedAt")
            FROM (
              SELECT
                attachment.id::text AS id,
                attachment.client_attachment_id AS "clientAttachmentId",
                attachment.document_kind AS "documentKind",
                attachment.expense_kind AS "expenseKind",
                attachment.description,
                attachment.document_date AS "documentDate",
                attachment.amount,
                attachment.currency_code AS "currencyCode",
                attachment.exchange_rate AS "exchangeRate",
                COALESCE(
                  attachment.amount_czk,
                  attachment.amount * CASE
                    WHEN COALESCE(attachment.currency_code, 'CZK') = 'CZK' THEN 1
                    ELSE COALESCE(attachment.exchange_rate, 1)
                  END
                ) AS "amountCzk",
                attachment.file_name AS "fileName",
                attachment.helios_expense_code_id AS "heliosExpenseCodeId",
                attachment.helios_expense_code_label AS "heliosExpenseCodeLabel",
                attachment.content_type AS "contentType",
                attachment.byte_size AS "byteSize",
                attachment.sha256,
                attachment.uploaded_at AS "uploadedAt"
              FROM travel.travel_attachment attachment
              WHERE attachment.travel_order_id = order_row.id
              ORDER BY attachment.uploaded_at
            ) attachment_row
          ), '[]'::jsonb) AS attachments
        FROM selected
        JOIN order_row ON order_row.id = selected.travel_order_id
        JOIN travel.app_user owner ON owner.id = order_row.owner_user_id
        JOIN travel.app_user approver ON approver.id = selected.approver_user_id
        LEFT JOIN travel.employee_profile ep ON ep.id = order_row.employee_profile_id
      ) t;
    """
    detail = run_psql_json(
        sql,
        {
            "approval_request_id": request_id,
            "user_id": user["user_id"],
            "can_review_any": "true" if can_review_any else "false",
        },
    )
    if not detail:
        return jsonify({"error": "approval_request_not_found"}), 404
    return jsonify(detail)


@app.get("/api/notifications")
@require_auth
def notifications():
    user_id = request.current_user["user_id"]
    sql = """
      WITH visible_notifications AS (
        SELECT n.*
        FROM travel.notification n
        WHERE n.recipient_user_id = :'user_id'::uuid
          AND n.read_at IS NULL
          AND n.status IN ('queued', 'sent', 'failed')
          AND (
            n.type_code <> 'approval_requested'
            OR EXISTS (
              SELECT 1
              FROM travel.approval_request ar
              JOIN travel.travel_order o ON o.id = ar.travel_order_id
              WHERE ar.travel_order_id = n.object_id
                AND ar.approver_user_id = n.recipient_user_id
                AND ar.status = 'pending'
                AND o.owner_user_id <> n.recipient_user_id
            )
          )
      )
      SELECT jsonb_build_object(
        'badge', COALESCE((SELECT to_jsonb(b) FROM (
          SELECT
            count(*) FILTER (WHERE status IN ('queued', 'sent')) AS unread_count,
            count(*) FILTER (WHERE status = 'failed') AS failed_count
          FROM visible_notifications
        ) b), '{"unread_count":0,"failed_count":0}'::jsonb),
        'items', COALESCE((SELECT jsonb_agg(to_jsonb(n)) FROM (
          SELECT
            id::text,
            channel,
            status,
            type_code,
            title,
            message,
            object_type,
            object_id::text,
            action_url,
            scheduled_for,
            sent_at,
            read_at,
            created_at
          FROM visible_notifications
          ORDER BY created_at DESC
          LIMIT 20
        ) n), '[]'::jsonb)
      )::text;
    """
    return jsonify(run_psql_json(sql, {"user_id": user_id}))


@app.get("/api/foreign-travel/reference")
@require_auth
def foreign_travel_reference():
    target_date = normalize_date_string(request.args.get("date")) or datetime.now().date().isoformat()
    countries = fetch_erp_foreign_countries(target_date)
    expense_codes = fetch_erp_expense_codes()
    currencies = fetch_erp_currencies()
    return jsonify({
        "date": target_date,
        "countries": countries,
        "expenseCodes": expense_codes,
        "currencies": currencies,
    })


@app.get("/api/foreign-travel/exchange-rate")
@require_auth
def foreign_travel_exchange_rate():
    currency = normalize_currency_code(request.args.get("currency"))
    target_date = normalize_date_string(request.args.get("date")) or datetime.now().date().isoformat()
    return jsonify(fetch_erp_exchange_rate(currency, target_date))


def fetch_erp_foreign_countries(target_date: str) -> list[dict]:
    view = quote_mssql_identifier(ERP_FOREIGN_COUNTRIES_VIEW)
    sql = f"""
      SET NOCOUNT ON;
      WITH ranked AS (
        SELECT
          id,
          KodZeme,
          Mena,
          Stravne,
          PlatnostDo,
          ROW_NUMBER() OVER (
            PARTITION BY KodZeme
            ORDER BY
              CASE WHEN PlatnostDo >= CONVERT(date, :'target_date') OR PlatnostDo IS NULL THEN 0 ELSE 1 END,
              CASE WHEN PlatnostDo >= CONVERT(date, :'target_date') OR PlatnostDo IS NULL THEN PlatnostDo END ASC,
              PlatnostDo DESC,
              id DESC
          ) AS rn
        FROM {view}
        WHERE COALESCE(KodZeme, N'') <> N''
      )
      SELECT
        id,
        KodZeme AS code,
        KodZeme AS label,
        Mena AS currencyCode,
        Stravne AS mealRate,
        PlatnostDo AS validTo
      FROM ranked
      WHERE rn = 1
      ORDER BY KodZeme
      FOR JSON PATH, INCLUDE_NULL_VALUES;
    """
    rows = run_sqlcmd_json(sql, {"target_date": target_date}) or []
    exchange_cache: dict[str, dict] = {}
    countries = []
    for row in rows:
        currency = normalize_currency_code(row.get("currencyCode"))
        if currency not in exchange_cache:
            exchange_cache[currency] = fetch_erp_exchange_rate(currency, target_date)
        rate = exchange_cache[currency]
        countries.append({
            "id": row.get("id"),
            "code": str(row.get("code") or "").strip(),
            "label": str(row.get("label") or row.get("code") or "").strip(),
            "currencyCode": currency,
            "mealRate": number_like(row.get("mealRate")),
            "validTo": str(row.get("validTo") or "")[:10],
            "exchangeRate": rate.get("exchangeRate", "1"),
            "exchangeRateDate": rate.get("exchangeRateDate") or "",
            "currencyUnit": rate.get("currencyUnit", 1),
        })
    return countries


def fetch_erp_expense_codes() -> list[dict]:
    view = quote_mssql_identifier(ERP_EXPENSE_CODES_VIEW)
    sql = f"""
      SET NOCOUNT ON;
      SELECT
        id,
        Kod AS code,
        Popis AS label
      FROM {view}
      WHERE COALESCE(Popis, N'') <> N''
      ORDER BY Popis, Kod
      FOR JSON PATH, INCLUDE_NULL_VALUES;
    """
    rows = run_sqlcmd_json(sql) or []
    return [
        {
            "id": row.get("id"),
            "code": str(row.get("code") or "").strip(),
            "label": str(row.get("label") or "").strip(),
        }
        for row in rows
        if row.get("id") is not None
    ]


def fetch_erp_currencies() -> list[str]:
    view = quote_mssql_identifier(ERP_EXCHANGE_RATES_VIEW)
    sql = f"""
      SET NOCOUNT ON;
      SELECT DISTINCT
        Mena AS currencyCode
      FROM {view}
      WHERE COALESCE(Mena, N'') <> N''
      ORDER BY Mena
      FOR JSON PATH, INCLUDE_NULL_VALUES;
    """
    rows = run_sqlcmd_json(sql) or []
    currencies = ["CZK"]
    for row in rows:
        currency = normalize_currency_code(row.get("currencyCode"))
        if currency not in currencies:
            currencies.append(currency)
    return currencies


def fetch_erp_exchange_rate(currency: str, target_date: str) -> dict:
    currency = normalize_currency_code(currency)
    if currency == "CZK":
        return {
            "currencyCode": "CZK",
            "exchangeRate": "1",
            "exchangeRateDate": target_date,
            "currencyUnit": 1,
        }

    view = quote_mssql_identifier(ERP_EXCHANGE_RATES_VIEW)
    sql = f"""
      SET NOCOUNT ON;
      SELECT TOP (1)
        Mena AS currencyCode,
        JednotkaMeny AS currencyUnit,
        Kurz AS exchangeRate,
        Datum AS exchangeRateDate
      FROM {view}
      WHERE Mena = :'currency'
        AND Datum <= CONVERT(date, :'target_date')
        AND COALESCE(Kurz, 0) <> 0
      ORDER BY Datum DESC, ID DESC
      FOR JSON PATH, WITHOUT_ARRAY_WRAPPER, INCLUDE_NULL_VALUES;
    """
    row = run_sqlcmd_json(sql, {"currency": currency, "target_date": target_date}) or {}
    unit = int(float(number_like(row.get("currencyUnit") or 1))) or 1
    raw_rate = float(number_like(row.get("exchangeRate")))
    exchange_rate = raw_rate / unit if unit and raw_rate else 1
    return {
        "currencyCode": currency,
        "exchangeRate": number_like(exchange_rate),
        "exchangeRateDate": str(row.get("exchangeRateDate") or target_date)[:10],
        "currencyUnit": unit,
        "rawExchangeRate": number_like(raw_rate),
    }


def normalize_date_string(value: object) -> str:
    text = str(value or "").strip()[:10]
    return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else ""


@app.get("/helios/preview")
@require_helios_preview_access
def helios_order_preview():
    import_id = valid_uuid(request.args.get("importId") or request.args.get("id") or request.args.get("travelOrderId"))
    helios_id = str(request.args.get("heliosId") or request.args.get("tabICestakId") or "").strip()
    if not import_id and not re.fullmatch(r"\d{1,20}", helios_id):
        return Response("ChybĂ­ nebo je neplatnĂ˝ ImportId.", status=400, mimetype="text/plain")

    order = load_helios_preview_order(import_id) if import_id else load_helios_preview_order_by_helios_id(helios_id)
    if not order:
        return Response("CestovnĂ­ pĹ™Ă­kaz nebyl nalezen.", status=404, mimetype="text/plain")

    return Response(render_helios_preview_html(order), mimetype="text/html; charset=utf-8")


@app.get("/helios/preview/<travel_order_id>/attachments/<attachment_id>")
@require_helios_preview_access
def helios_order_preview_attachment(travel_order_id, attachment_id):
    order_id = valid_uuid(travel_order_id)
    file_id = valid_uuid(attachment_id)
    if not order_id or not file_id:
        return Response("NeplatnĂ˝ identifikĂˇtor pĹ™Ă­lohy.", status=400, mimetype="text/plain")

    sql = """
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT
          attachment.file_name,
          attachment.content_type,
          attachment.storage_key
        FROM travel.travel_attachment attachment
        WHERE attachment.travel_order_id = :'travel_order_id'::uuid
          AND attachment.id = :'attachment_id'::uuid
      ) t;
    """
    attachment = run_psql_json(sql, {"travel_order_id": order_id, "attachment_id": file_id})
    if not attachment:
        return Response("PĹ™Ă­loha nebyla nalezena.", status=404, mimetype="text/plain")

    target = (ATTACHMENT_DIR / attachment["storage_key"]).resolve()
    attachment_root = ATTACHMENT_DIR.resolve()
    if attachment_root not in target.parents or not target.exists():
        return Response("Soubor pĹ™Ă­lohy nebyl nalezen.", status=404, mimetype="text/plain")

    return send_file(
        target,
        mimetype=attachment.get("content_type") or "application/octet-stream",
        download_name=attachment.get("file_name") or "doklad",
        as_attachment=False,
    )


def load_helios_preview_order(import_id: str) -> dict | None:
    sql = """
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT
          o.id::text AS id,
          o.order_no AS "orderNo",
          o.status::text AS status,
          o.export_status::text AS "exportStatus",
          o.submitted_at AS "submittedAt",
          o.approved_at AS "approvedAt",
          o.helios_document_id AS "heliosDocumentId",
          o.helios_exported_at AS "heliosExportedAt",
          jsonb_build_object(
            'purpose', o.purpose,
            'destination', o.destination,
            'visitedCompanies', o.visited_companies,
            'companions', o.companions,
            'plannedStartAt', o.planned_start_at,
            'plannedEndAt', o.planned_end_at,
            'reportDate', o.report_date,
            'currencyCode', o.currency_code
          ) AS trip,
          jsonb_build_object(
            'displayName', COALESCE(ep.display_name, owner.display_name),
            'email', COALESCE(ep.email::text, owner.email::text),
            'personalNumber', ep.personal_number,
            'personalNumberVerifiedFromErp',
              ep.personal_number ~ '^[0-9]+$'
              AND ep.helios_employee_id IS NOT NULL
              AND ep.last_synced_at IS NOT NULL
              AND owner.helios_personal_number = ep.personal_number,
            'organization', ep.organization_name,
            'costCenterCode', COALESCE(ep.cost_center_code, cost_center.code),
            'costCenterName', COALESCE(ep.cost_center_name, cost_center.name),
            'department', ep.department_name,
            'address', ep.address,
            'phone', ep.phone
          ) AS employee,
          COALESCE((
            SELECT jsonb_build_object(
              'name', approver.display_name,
              'email', approver.email::text,
              'status', ar.status::text,
              'requestedAt', ar.requested_at,
              'decidedAt', ar.decided_at,
              'comment', ar.decision_comment
            )
            FROM travel.approval_request ar
            JOIN travel.app_user approver ON approver.id = ar.approver_user_id
            WHERE ar.travel_order_id = o.id
            ORDER BY ar.decided_at DESC NULLS LAST, ar.requested_at DESC
            LIMIT 1
          ), '{}'::jsonb) AS approval,
          COALESCE(total.calculation_snapshot #> '{order,vehicle}', '{}'::jsonb)
            || jsonb_build_object(
              'heliosId', COALESCE(used_vehicle.helios_id, ''),
              'sourceSystem', COALESCE(used_vehicle.source_system::text, ''),
              'heliosExportStatus', COALESCE(used_vehicle.helios_export_status::text, 'not_ready'),
              'isPrivate', COALESCE(used_vehicle.is_private, true)
            ) AS vehicle,
          jsonb_build_object(
            'totalKm', COALESCE(total.total_km, 0),
            'totalHours', COALESCE(total.total_hours, 0),
            'transportAmount', COALESCE(total.transport_amount, 0),
            'mealAmount', COALESCE(total.meal_amount, 0),
            'lodgingAmount', COALESCE(total.lodging_amount, 0),
            'otherAmount', COALESCE(total.other_amount, 0),
            'grossAmount', COALESCE(total.gross_amount, 0),
            'advanceAmount', COALESCE(total.advance_amount, o.advance_amount, 0),
            'balanceAmount', COALESCE(total.balance_amount, 0),
            'balanceRounded', COALESCE(total.balance_rounded, 0)
          ) AS totals,
          COALESCE((
            SELECT jsonb_agg(
              jsonb_build_object(
                'sequenceNo', line.sequence_no,
                'segmentType', line.segment_type::text,
                'countryCode', line.foreign_country_code,
                'countryName', line.foreign_country_name,
                'foreignCurrencyCode', line.foreign_meal_currency,
                'foreignMealRate', line.foreign_meal_rate,
                'foreignExchangeRate', line.foreign_exchange_rate,
                'foreignExchangeRateDate', line.foreign_exchange_rate_date,
                'foreignMealAmountCzk', line.foreign_meal_amount_czk,
                'transport', line.transport_kind::text,
                'startAt', line.start_at,
                'endAt', line.end_at,
                'from', line.from_place,
                'to', line.to_place,
                'company', line.company_or_place,
                'purpose', line.purpose,
                'km', line.km,
                'fareAmount', line.fare_amount,
                'lodgingAmount', line.lodging_amount,
                'otherAmount', line.other_amount,
                'freeMeals', line.free_meals,
                'calculatedHours', line.calculated_hours,
                'mealAmount', line.calculated_meal_amount,
                'mealAmountForeign', CASE
                  WHEN line.segment_type = 'foreign' THEN COALESCE((line.calculation_detail->>'mealForeignAmount')::numeric, line.foreign_meal_rate, line.calculated_meal_amount)
                  ELSE line.calculated_meal_amount
                END,
                'mealCurrency', COALESCE(line.calculation_detail->>'mealCurrency', line.foreign_meal_currency, o.currency_code),
                'mealExchangeRate', COALESCE((line.calculation_detail->>'mealExchangeRate')::numeric, line.foreign_exchange_rate, 1),
                'privateVehicleAmount', line.calculated_private_vehicle_amount,
                'totalAmount', line.calculated_total_amount
              )
              ORDER BY line.sequence_no
            )
            FROM travel.travel_route_line line
            WHERE line.travel_order_id = o.id
          ), '[]'::jsonb) AS "routeLines",
          COALESCE((
            SELECT jsonb_agg(
              jsonb_build_object(
                'id', attachment.id::text,
                'documentKind', attachment.document_kind,
                'expenseKind', attachment.expense_kind,
                'description', attachment.description,
                'documentDate', attachment.document_date,
                'amount', attachment.amount,
                'currencyCode', COALESCE(attachment.currency_code, o.currency_code, 'CZK'),
                'exchangeRate', CASE
                  WHEN COALESCE(attachment.currency_code, o.currency_code, 'CZK') = 'CZK' THEN 1
                  ELSE COALESCE(attachment.exchange_rate, 1)
                END,
                'amountCzk', COALESCE(
                  attachment.amount_czk,
                  attachment.amount * CASE
                    WHEN COALESCE(attachment.currency_code, o.currency_code, 'CZK') = 'CZK' THEN 1
                    ELSE COALESCE(attachment.exchange_rate, 1)
                  END
                ),
                'fileName', attachment.file_name,
                'heliosExpenseCodeId', attachment.helios_expense_code_id,
                'heliosExpenseCodeLabel', attachment.helios_expense_code_label,
                'contentType', attachment.content_type,
                'byteSize', attachment.byte_size,
                'uploadedAt', attachment.uploaded_at
              )
              ORDER BY attachment.uploaded_at
            )
            FROM travel.travel_attachment attachment
            WHERE attachment.travel_order_id = o.id
          ), '[]'::jsonb) AS attachments
        FROM travel.travel_order o
        JOIN travel.app_user owner ON owner.id = o.owner_user_id
        LEFT JOIN travel.employee_profile ep ON ep.id = o.employee_profile_id
        LEFT JOIN travel.cost_center cost_center ON cost_center.id = o.cost_center_id
        LEFT JOIN travel.travel_order_total total ON total.travel_order_id = o.id
        LEFT JOIN travel.vehicle used_vehicle
          ON used_vehicle.id = CASE
            WHEN (total.calculation_snapshot #>> '{order,vehicle,id}')
              ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
            THEN (total.calculation_snapshot #>> '{order,vehicle,id}')::uuid
            ELSE NULL::uuid
          END
        WHERE o.id = :'import_id'::uuid
      ) t;
    """
    return run_psql_json(sql, {"import_id": import_id}) or None


def load_helios_preview_order_by_helios_id(helios_id: str) -> dict | None:
    sql = """
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT id::text AS id
        FROM travel.travel_order
        WHERE helios_document_id = :'helios_id'
        ORDER BY helios_exported_at DESC NULLS LAST, updated_at DESC
        LIMIT 1
      ) t;
    """
    row = run_psql_json(sql, {"helios_id": helios_id})
    return load_helios_preview_order(row["id"]) if row and row.get("id") else None


def render_helios_preview_html(order: dict) -> str:
    token = str(request.args.get("token") or "").strip()
    order_id = str(order.get("id") or "")
    title = f"NĂˇhled cestovnĂ­ho pĹ™Ă­kazu {order.get('orderNo') or ''}".strip()
    attachment_count = len(order.get("attachments") or [])
    rows = "".join(render_preview_route_line(line) for line in order.get("routeLines") or [])
    attachments = "".join(render_preview_attachment(order_id, token, attachment) for attachment in order.get("attachments") or [])
    if not attachments:
        attachments = '<p class="muted">K cestovnĂ­mu pĹ™Ă­kazu nejsou pĹ™iloĹľenĂ© doklady.</p>'

    totals = order.get("totals") or {}
    employee = order.get("employee") or {}
    trip = order.get("trip") or {}
    approval = order.get("approval") or {}
    vehicle = order.get("vehicle") or {}

    return f"""<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape_html(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #122033;
      --muted: #607084;
      --line: #d8e4ef;
      --panel: #ffffff;
      --soft: #f4f8fb;
      --accent: #03bfe8;
      --violet: #8254ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      color: var(--ink);
      background: linear-gradient(120deg, #f7fbff 0%, #eef7fb 100%);
    }}
    main {{
      width: min(1180px, calc(100% - 32px));
      margin: 24px auto 40px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: flex-start;
      padding: 24px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 14px 35px rgba(18, 32, 51, 0.08);
    }}
    h1, h2 {{ margin: 0; }}
    h1 {{ font-size: clamp(24px, 4vw, 38px); }}
    h2 {{ font-size: 18px; margin-bottom: 14px; }}
    .brand {{ color: var(--muted); font-size: 13px; margin: 0 0 8px; text-transform: uppercase; letter-spacing: .08em; }}
    .status {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border: 1px solid rgba(3, 191, 232, .45);
      border-radius: 999px;
      color: #025d77;
      background: #e9faff;
      font-weight: 700;
      white-space: nowrap;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-top: 16px;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 18px;
      min-width: 0;
    }}
    .wide {{ grid-column: span 2; }}
    .full {{ grid-column: 1 / -1; }}
    dl {{
      display: grid;
      grid-template-columns: minmax(130px, 190px) 1fr;
      gap: 8px 14px;
      margin: 0;
    }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; min-width: 0; overflow-wrap: anywhere; font-weight: 600; }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
    }}
    .kpi {{
      padding: 14px;
      border-radius: 8px;
      background: var(--soft);
      border: 1px solid var(--line);
    }}
    .kpi span {{ display: block; color: var(--muted); font-size: 12px; }}
    .kpi strong {{ display: block; margin-top: 5px; font-size: 18px; overflow-wrap: anywhere; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    th, td {{
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }}
    th {{ color: var(--muted); font-size: 12px; font-weight: 700; }}
    .attachments {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .attachment {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
      min-width: 0;
    }}
    .attachment iframe,
    .attachment img {{
      width: 100%;
      min-height: 360px;
      max-height: 620px;
      margin-top: 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--soft);
      object-fit: contain;
    }}
    .attachment img {{ height: auto; min-height: 0; }}
    .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      padding: 8px 12px;
      border-radius: 6px;
      border: 1px solid var(--accent);
      color: #005a72;
      text-decoration: none;
      font-weight: 700;
      background: #effcff;
    }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 920px) {{
      header {{ flex-direction: column; }}
      .grid {{ grid-template-columns: 1fr; }}
      .wide {{ grid-column: auto; }}
      .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .attachments {{ grid-template-columns: 1fr; }}
      dl {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; white-space: nowrap; }}
    }}
    @media print {{
      body {{ background: #fff; }}
      main {{ width: auto; margin: 0; }}
      header, .card, .attachment {{ box-shadow: none; break-inside: avoid; }}
      .button {{ display: none; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <p class="brand">Oresi Â· CestovnĂ­ pĹ™Ă­kazy</p>
        <h1>{escape_html(order.get("orderNo") or "Bez ÄŤĂ­sla")}</h1>
        <p class="muted">{escape_html(trip.get("purpose") or "Bez ĂşÄŤelu")} Â· {escape_html(trip.get("destination") or "Bez cĂ­le")}</p>
      </div>
      <div class="status">{escape_html(status_label(order.get("status")))} Â· {escape_html(export_status_label(order.get("exportStatus")))}</div>
    </header>

    <section class="grid">
      <article class="card wide">
        <h2>ZamÄ›stnanec</h2>
        <dl>
          {preview_field("JmĂ©no", employee.get("displayName"))}
          {preview_field("OsobnĂ­ ÄŤĂ­slo", employee.get("personalNumber"))}
          {preview_field("OvÄ›Ĺ™eno v ERP", "ano" if employee.get("personalNumberVerifiedFromErp") else "ne")}
          {preview_field("E-mail", employee.get("email"))}
          {preview_field("Organizace", employee.get("organization"))}
          {preview_field("StĹ™edisko", join_nonempty(employee.get("costCenterCode"), employee.get("costCenterName")))}
          {preview_field("Adresa", employee.get("address"))}
        </dl>
      </article>

      <article class="card wide">
        <h2>Cesta a schvĂˇlenĂ­</h2>
        <dl>
          {preview_field("Od", format_datetime(trip.get("plannedStartAt")))}
          {preview_field("Do", format_datetime(trip.get("plannedEndAt")))}
          {preview_field("NavĹˇtĂ­venĂ© firmy", trip.get("visitedCompanies"))}
          {preview_field("SpolucestujĂ­cĂ­", trip.get("companions"))}
          {preview_field("Schvalovatel", approval.get("name"))}
          {preview_field("SchvĂˇleno", format_datetime(approval.get("decidedAt") or order.get("approvedAt")))}
        </dl>
      </article>

      <article class="card full">
        <h2>Souhrn</h2>
        <div class="kpis">
          {preview_kpi("Km", format_number(totals.get("totalKm"), 0))}
          {preview_kpi("CestovnĂ©", format_money(totals.get("transportAmount")))}
          {preview_kpi("StravnĂ©", format_money(totals.get("mealAmount")))}
          {preview_kpi("OstatnĂ­ + doklady", format_money(totals.get("otherAmount")))}
          {preview_kpi("K vĂ˝platÄ›", format_money(totals.get("balanceRounded")))}
        </div>
      </article>

      <article class="card wide">
        <h2>Vozidlo</h2>
        <dl>
          {preview_field("Popis", vehicle.get("brand"))}
          {preview_field("SPZ", vehicle.get("plate"))}
          {preview_field("Palivo", vehicle.get("fuelType"))}
          {preview_field("SpotĹ™eba", vehicle.get("consumption"))}
          {preview_field("Cena PHM", format_money(vehicle.get("fuelPrice")) if vehicle.get("fuelPrice") not in (None, "") else "")}
          {preview_field("Helios ID", vehicle.get("heliosId"))}
        </dl>
      </article>

      <article class="card wide">
        <h2>ImportnĂ­ kontrola</h2>
        <dl>
          {preview_field("ImportId", order_id)}
          {preview_field("Helios cestĂˇk ID", order.get("heliosDocumentId"))}
          {preview_field("NaimportovĂˇno", format_datetime(order.get("heliosExportedAt")))}
          {preview_field("PoÄŤet pĹ™Ă­loh", attachment_count)}
        </dl>
      </article>

      <article class="card full">
        <h2>ĹĂˇdky vyĂşÄŤtovĂˇnĂ­</h2>
        <table>
          <thead>
            <tr>
              <th>#</th><th>Typ</th><th>Odjezd</th><th>PĹ™Ă­jezd</th><th>Odkud</th><th>Kam</th><th>Doprava</th><th>Km</th><th>Celkem</th>
            </tr>
          </thead>
          <tbody>{rows or '<tr><td colspan="9" class="muted">Nejsou zadanĂ© ĹľĂˇdnĂ© Ĺ™Ăˇdky.</td></tr>'}</tbody>
        </table>
      </article>

      <article class="card full">
        <h2>Doklady a pĹ™Ă­lohy</h2>
        <div class="attachments">{attachments}</div>
      </article>
    </section>
  </main>
</body>
</html>"""


def render_preview_route_line(line: dict) -> str:
    return f"""
      <tr>
        <td>{escape_html(line.get("sequenceNo"))}</td>
        <td>{escape_html(segment_type_label(line.get("segmentType")))}</td>
        <td>{escape_html(format_datetime(line.get("startAt")))}</td>
        <td>{escape_html(format_datetime(line.get("endAt")))}</td>
        <td>{escape_html(line.get("from"))}</td>
        <td>{escape_html(line.get("to"))}</td>
        <td>{escape_html(transport_label(line.get("transport")))}</td>
        <td>{escape_html(format_number(line.get("km"), 0))}</td>
        <td>{escape_html(format_money(line.get("totalAmount")))}</td>
      </tr>
    """


def render_preview_attachment(order_id: str, token: str, attachment: dict) -> str:
    attachment_id = str(attachment.get("id") or "")
    token_query = f"?token={quote(token, safe='')}" if token else ""
    url = f"/helios/preview/{quote(order_id, safe='')}/attachments/{quote(attachment_id, safe='')}{token_query}"
    content_type = str(attachment.get("contentType") or "").lower()
    file_name = str(attachment.get("fileName") or "Doklad")
    preview = ""
    if content_type.startswith("image/"):
        preview = f'<img src="{escape_html(url)}" alt="{escape_html(file_name)}" loading="lazy" />'
    elif content_type == "application/pdf" or file_name.lower().endswith(".pdf"):
        preview = f'<iframe src="{escape_html(url)}" title="{escape_html(file_name)}"></iframe>'

    return f"""
      <section class="attachment">
        <h3>{escape_html(file_name)}</h3>
        <p class="muted">
          {escape_html(expense_kind_label(attachment.get("expenseKind")))}
          Â· {escape_html(document_kind_label(attachment.get("documentKind")))}
          Â· {escape_html(format_date(attachment.get("documentDate")))}
        </p>
        <p>
          <strong>{escape_html(format_money(attachment.get("amount"), attachment.get("currencyCode")))}</strong>
          <span class="muted">pĹ™epoÄŤet {escape_html(format_money(attachment.get("amountCzk")))}</span>
        </p>
        {f'<p>{escape_html(attachment.get("description"))}</p>' if attachment.get("description") else ''}
        <a class="button" href="{escape_html(url)}" target="_blank" rel="noopener">OtevĹ™Ă­t soubor</a>
        {preview}
      </section>
    """


def preview_field(label: str, value: object) -> str:
    return f"<dt>{escape_html(label)}</dt><dd>{escape_html(value) if value not in (None, '') else '<span class=\"muted\">neuvedeno</span>'}</dd>"


def preview_kpi(label: str, value: object) -> str:
    return f'<div class="kpi"><span>{escape_html(label)}</span><strong>{escape_html(value)}</strong></div>'


def escape_html(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def join_nonempty(*values: object) -> str:
    return " Â· ".join(str(value) for value in values if value not in (None, ""))


def format_datetime(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("T", " ")[:16]


def format_date(value: object) -> str:
    return str(value or "").strip()[:10]


def format_number(value: object, decimals: int = 2) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0
    if decimals == 0:
        return f"{number:,.0f}".replace(",", " ")
    return f"{number:,.{decimals}f}".replace(",", " ").replace(".", ",")


def format_money(value: object, currency: object = "CZK") -> str:
    code = str(currency or "CZK").strip().upper()[:3] or "CZK"
    return f"{format_number(value, 2)} {code}"


def status_label(value: object) -> str:
    return {
        "draft": "RozpracovĂˇno",
        "submitted": "Ke schvĂˇlenĂ­",
        "approved": "SchvĂˇleno",
        "settlement": "VyĂşÄŤtovĂˇnĂ­",
        "closed": "UzavĹ™eno",
        "rejected": "ZamĂ­tnuto",
        "cancelled": "ZruĹˇeno",
    }.get(str(value or ""), str(value or ""))


def export_status_label(value: object) -> str:
    return {
        "not_ready": "NepĹ™ipraveno",
        "ready": "PĹ™ipraveno",
        "queued": "Ve frontÄ›",
        "exported": "NaimportovĂˇno",
        "failed": "Chyba importu",
        "cancelled": "ZruĹˇeno",
    }.get(str(value or ""), str(value or ""))


def segment_type_label(value: object) -> str:
    return {"private": "SoukromĂ˝", "domestic": "TuzemskĂ˝", "foreign": "ZahraniÄŤnĂ­"}.get(str(value or ""), str(value or ""))


def transport_label(value: object) -> str:
    return {
        "private_car": "SoukromĂ© vozidlo",
        "company_car": "SluĹľebnĂ­ vozidlo",
        "public_transport": "VeĹ™ejnĂˇ doprava",
        "taxi": "Taxi",
        "plane": "Letadlo",
        "other": "JinĂ©",
    }.get(str(value or ""), str(value or ""))


def expense_kind_label(value: object) -> str:
    return {
        "fuel": "PHM / energie",
        "fare": "JĂ­zdnĂ©",
        "lodging": "UbytovĂˇnĂ­",
        "parking": "ParkovnĂ©",
        "meal": "StravovĂˇnĂ­",
        "other": "OstatnĂ­ vĂ˝daj",
    }.get(str(value or ""), str(value or ""))


def document_kind_label(value: object) -> str:
    return {"receipt": "ĂšÄŤtenka", "invoice": "Faktura", "ticket": "JĂ­zdenka", "other": "JinĂ˝ doklad"}.get(str(value or ""), str(value or ""))


@app.get("/api/helios/import-candidates")
@require_helios_import_access
def helios_import_candidates():
    raw_limit = request.args.get("limit", "100")
    try:
        limit = max(1, min(int(raw_limit), 500))
    except ValueError:
        return jsonify({"error": "invalid_limit"}), 400
    shape = str(request.args.get("shape") or request.args.get("view") or "full").strip().lower()

    if shape in {"list", "summary"}:
        sql = """
          WITH candidates AS (
            SELECT o.*
            FROM travel.travel_order o
            JOIN travel.app_user owner_verify ON owner_verify.id = o.owner_user_id
            JOIN travel.employee_profile ep_verify ON ep_verify.id = o.employee_profile_id
            WHERE o.status = 'approved'
              AND o.helios_document_id IS NULL
              AND o.export_status <> 'exported'
              AND ep_verify.personal_number ~ '^[0-9]+$'
              AND ep_verify.helios_employee_id IS NOT NULL
              AND ep_verify.last_synced_at IS NOT NULL
              AND owner_verify.helios_personal_number = ep_verify.personal_number
              AND EXISTS (
                SELECT 1
                FROM travel.approval_request approved_request
                WHERE approved_request.travel_order_id = o.id
                  AND approved_request.status = 'approved'
                  AND approved_request.approver_user_id <> o.owner_user_id
              )
            ORDER BY COALESCE(o.approved_at, o.updated_at) DESC, o.order_no
            LIMIT :'limit'::integer
          ),
          items AS (
            SELECT
              COALESCE(o.approved_at, o.updated_at) AS sort_at,
              jsonb_build_object(
                'importId', o.id::text,
                'orderNo', o.order_no,
                'status', o.status::text,
                'exportStatus', o.export_status::text,
                'approvedAt', o.approved_at,
                'submittedAt', o.submitted_at,
                'cisloCestovnihoPrikazu', o.order_no,
                'cisloZamestnance',
                  CASE WHEN ep.personal_number ~ '^[0-9]+$' THEN ep.personal_number::integer ELSE NULL END,
                'osobniCisloVAplikaci', ep.personal_number,
                'osobniCisloOverenoVErp', true,
                'zamestnanec', COALESCE(ep.display_name, owner.display_name),
                'email', COALESCE(ep.email::text, owner.email::text),
                'organizace', ep.organization_name,
                'strediskoZamestnance', COALESCE(ep.cost_center_code, cost_center.code),
                'strediskoNazev', COALESCE(ep.cost_center_name, cost_center.name),
                'utvar', ep.department_name,
                'ucelCesty', o.purpose,
                'cilCesty', left(COALESCE(o.destination, o.purpose, ''), 60),
                'cilCestyPlnyText', o.destination,
                'navstiveneFirmy', o.visited_companies,
                'spolucestujici', o.companions,
                'datVystDokl', COALESCE(o.approved_at, o.updated_at),
                'datCasPocatek', o.planned_start_at,
                'datCasKonec', o.planned_end_at,
                'stredisko', COALESCE(ep.cost_center_code, cost_center.code),
                'typCesty',
                  CASE WHEN EXISTS (
                    SELECT 1 FROM travel.travel_route_line foreign_line
                    WHERE foreign_line.travel_order_id = o.id
                      AND foreign_line.segment_type = 'foreign'
                  ) THEN 'Z' ELSE 'T' END,
                'typDopravy',
                  CASE
                    WHEN EXISTS (
                      SELECT 1 FROM travel.travel_route_line car_line
                      WHERE car_line.travel_order_id = o.id
                        AND car_line.transport_kind IN ('private_car', 'company_car')
                    ) THEN 'S'
                    WHEN EXISTS (
                      SELECT 1 FROM travel.travel_route_line public_line
                      WHERE public_line.travel_order_id = o.id
                        AND public_line.transport_kind = 'public_transport'
                    ) THEN 'V'
                    ELSE 'J'
                  END,
                'spz', COALESCE(total.calculation_snapshot #>> '{order,vehicle,plate}', ''),
                'kmCelkem', COALESCE(total.total_km, 0),
                'kmZahr', COALESCE((
                  SELECT sum(foreign_km.km)
                  FROM travel.travel_route_line foreign_km
                  WHERE foreign_km.travel_order_id = o.id
                    AND foreign_km.segment_type = 'foreign'
                ), 0),
                'spotreba', NULLIF(total.calculation_snapshot #>> '{order,vehicle,consumption}', '')::numeric,
                'cenaL', NULLIF(total.calculation_snapshot #>> '{order,vehicle,fuelPrice}', '')::numeric,
                'sazbaKm', NULLIF(total.calculation_snapshot #>> '{order,vehicle,basicKmRate}', '')::numeric,
                'phmKc', COALESCE(total.calculation_snapshot #>> '{calculation,totalFuel}', '0')::numeric,
                'celkemPhm', COALESCE(total.calculation_snapshot #>> '{calculation,totalFuel}', '0')::numeric,
                'celkemDiety', COALESCE(total.meal_amount, 0),
                'celkemNaklady', COALESCE(total.lodging_amount, 0) + COALESCE(total.other_amount, 0),
                'celkemNahrady',
                  COALESCE(NULLIF(total.calculation_snapshot #>> '{calculation,totalBasicKmComp}', '')::numeric, total.transport_amount, 0),
                'celkemPrepocet', COALESCE(total.gross_amount, 0),
                'menaPrepocet', o.currency_code,
                'kurzPrepocet', COALESCE(NULLIF(total.calculation_snapshot #>> '{order,trip,exchangeRate}', '')::numeric, 1),
                'hodinCelkem', COALESCE(total.total_hours, 0),
                'zaloha', COALESCE(total.advance_amount, o.advance_amount, 0),
                'doplatekNeboVratka', COALESCE(total.balance_amount, 0),
                'doplatekNeboVratkaZaokrouhlene', COALESCE(total.balance_rounded, 0)
              ) AS item
            FROM candidates o
            JOIN travel.app_user owner ON owner.id = o.owner_user_id
            JOIN travel.employee_profile ep ON ep.id = o.employee_profile_id
            LEFT JOIN travel.cost_center cost_center ON cost_center.id = o.cost_center_id
            LEFT JOIN travel.travel_order_total total ON total.travel_order_id = o.id
          )
          SELECT jsonb_build_object(
            'generatedAt', now(),
            'shape', 'list',
            'count', count(*),
            'items', COALESCE(jsonb_agg(item ORDER BY sort_at DESC), '[]'::jsonb)
          )::text
          FROM items;
        """
        return jsonify(run_psql_json(sql, {"limit": limit}))

    sql = """
      WITH candidates AS (
        SELECT o.*
        FROM travel.travel_order o
        JOIN travel.app_user owner_verify ON owner_verify.id = o.owner_user_id
        JOIN travel.employee_profile ep_verify ON ep_verify.id = o.employee_profile_id
        WHERE o.status = 'approved'
          AND o.helios_document_id IS NULL
          AND o.export_status <> 'exported'
          AND ep_verify.personal_number ~ '^[0-9]+$'
          AND ep_verify.helios_employee_id IS NOT NULL
          AND ep_verify.last_synced_at IS NOT NULL
          AND owner_verify.helios_personal_number = ep_verify.personal_number
          AND EXISTS (
            SELECT 1
            FROM travel.approval_request approved_request
            WHERE approved_request.travel_order_id = o.id
              AND approved_request.status = 'approved'
              AND approved_request.approver_user_id <> o.owner_user_id
          )
        ORDER BY COALESCE(o.approved_at, o.updated_at) DESC, o.order_no
        LIMIT :'limit'::integer
      ),
      items AS (
        SELECT
          COALESCE(o.approved_at, o.updated_at) AS sort_at,
          jsonb_build_object(
            'importId', o.id::text,
            'orderNo', o.order_no,
            'status', o.status::text,
            'exportStatus', o.export_status::text,
            'approvedAt', o.approved_at,
            'submittedAt', o.submitted_at,
            'trip', jsonb_build_object(
              'purpose', o.purpose,
              'destination', o.destination,
              'visitedCompanies', o.visited_companies,
              'companions', o.companions,
              'plannedStartAt', o.planned_start_at,
              'plannedEndAt', o.planned_end_at,
              'reportDate', o.report_date,
              'currencyCode', o.currency_code
            ),
            'employee', jsonb_build_object(
              'userId', owner.id::text,
              'displayName', COALESCE(ep.display_name, owner.display_name),
              'email', COALESCE(ep.email::text, owner.email::text),
              'personalNumber', ep.personal_number,
              'personalNumberVerifiedFromErp',
                ep.personal_number ~ '^[0-9]+$'
                AND ep.helios_employee_id IS NOT NULL
                AND ep.last_synced_at IS NOT NULL
                AND owner.helios_personal_number = ep.personal_number,
              'heliosEmployeeNumber',
                CASE WHEN ep.personal_number ~ '^[0-9]+$' THEN ep.personal_number::integer ELSE NULL END,
              'heliosEmployeeId', ep.helios_employee_id,
              'organization', ep.organization_name,
              'costCenterCode', COALESCE(ep.cost_center_code, cost_center.code),
              'costCenterName', COALESCE(ep.cost_center_name, cost_center.name),
              'department', ep.department_name,
              'address', ep.address,
              'phone', ep.phone
            ),
            'zakazka', jsonb_build_object(
              'table', 'TabZakazka',
              'rada', 'CPR',
              'cisloZakazky', o.order_no,
              'nazev', left(COALESCE(NULLIF(o.purpose, ''), o.order_no), 100)
            ),
            'vehicle',
              COALESCE(total.calculation_snapshot #> '{order,vehicle}', '{}'::jsonb)
              || jsonb_build_object(
                'heliosId', COALESCE(used_vehicle.helios_id, ''),
                'sourceSystem', COALESCE(used_vehicle.source_system::text, ''),
                'heliosExportStatus', COALESCE(used_vehicle.helios_export_status::text, 'not_ready'),
                'isPrivate', COALESCE(used_vehicle.is_private, true)
              ),
            'totals', jsonb_build_object(
              'totalKm', COALESCE(total.total_km, 0),
              'totalHours', COALESCE(total.total_hours, 0),
              'transportAmount', COALESCE(total.transport_amount, 0),
              'mealAmount', COALESCE(total.meal_amount, 0),
              'lodgingAmount', COALESCE(total.lodging_amount, 0),
              'otherAmount', COALESCE(total.other_amount, 0),
              'grossAmount', COALESCE(total.gross_amount, 0),
              'advanceAmount', COALESCE(total.advance_amount, o.advance_amount, 0),
              'balanceAmount', COALESCE(total.balance_amount, 0),
              'balanceRounded', COALESCE(total.balance_rounded, 0)
            ),
            'routeLines', COALESCE((
              SELECT jsonb_agg(
                jsonb_build_object(
                  'id', line.id::text,
                  'sequenceNo', line.sequence_no,
                  'segmentType', line.segment_type::text,
                  'countryCode', line.foreign_country_code,
                  'countryName', line.foreign_country_name,
                  'foreignCurrencyCode', line.foreign_meal_currency,
                  'foreignMealRate', line.foreign_meal_rate,
                  'foreignExchangeRate', line.foreign_exchange_rate,
                  'foreignExchangeRateDate', line.foreign_exchange_rate_date,
                  'foreignMealAmountCzk', line.foreign_meal_amount_czk,
                  'transport', line.transport_kind::text,
                  'startAt', line.start_at,
                  'endAt', line.end_at,
                  'from', line.from_place,
                  'to', line.to_place,
                  'company', line.company_or_place,
                  'purpose', line.purpose,
                  'km', line.km,
                  'fareAmount', line.fare_amount,
                  'lodgingAmount', line.lodging_amount,
                  'otherAmount', line.other_amount,
                  'freeMeals', line.free_meals,
                  'calculatedHours', line.calculated_hours,
                  'mealAmount', line.calculated_meal_amount,
                  'mealAmountForeign', CASE
                    WHEN line.segment_type = 'foreign' THEN COALESCE((line.calculation_detail->>'mealForeignAmount')::numeric, line.foreign_meal_rate, line.calculated_meal_amount)
                    ELSE line.calculated_meal_amount
                  END,
                  'mealCurrency', COALESCE(line.calculation_detail->>'mealCurrency', line.foreign_meal_currency, o.currency_code),
                  'mealExchangeRate', COALESCE((line.calculation_detail->>'mealExchangeRate')::numeric, line.foreign_exchange_rate, 1),
                  'privateVehicleAmount', line.calculated_private_vehicle_amount,
                  'totalAmount', line.calculated_total_amount,
                  'helios', jsonb_build_object(
                    'table', 'TabICestaUsek',
                    'values', jsonb_build_object(
                      'TypUseku', CASE line.segment_type::text
                        WHEN 'private' THEN 'S'
                        WHEN 'foreign' THEN 'Z'
                        ELSE 'T'
                      END,
                      'DatCasPocatek', line.start_at,
                      'DatCasKonec', line.end_at,
                      'odkud', line.from_place,
                      'kam', line.to_place,
                      'Mena', COALESCE(line.calculation_detail->>'mealCurrency', line.foreign_meal_currency, o.currency_code),
                      'Kurz', COALESCE((line.calculation_detail->>'mealExchangeRate')::numeric, line.foreign_exchange_rate, 1),
                      'KodZeme', line.foreign_country_code,
                      'Stravne', CASE
                        WHEN line.segment_type = 'foreign' THEN COALESCE((line.calculation_detail->>'mealForeignAmount')::numeric, line.foreign_meal_rate, line.calculated_meal_amount)
                        ELSE line.calculated_meal_amount
                      END,
                      'CelkemStravne', line.calculated_meal_amount,
                      'CelkemKC', line.calculated_meal_amount,
                      'Dny', 0,
                      'Hod1', COALESCE(line.calculated_hours, 0),
                      'Hod2', 0,
                      'ProcStrav',
                        CASE
                          WHEN COALESCE((line.calculation_detail->>'mealBase')::numeric, 0) > 0
                          THEN round((-100 * COALESCE((line.calculation_detail->>'mealReduction')::numeric, 0))
                            / NULLIF((line.calculation_detail->>'mealBase')::numeric, 0), 6)
                          ELSE 0
                        END,
                      'Snidane', false,
                      'Obed', false,
                      'Vecere', false,
                      'RucProc', line.free_meals = 0
                    )
                  )
                )
                ORDER BY line.sequence_no
              )
              FROM travel.travel_route_line line
              WHERE line.travel_order_id = o.id
            ), '[]'::jsonb),
            'attachments', COALESCE((
              SELECT jsonb_agg(
                jsonb_build_object(
                  'id', attachment.id::text,
                  'documentKind', attachment.document_kind,
                  'expenseKind', attachment.expense_kind,
                  'description', attachment.description,
                  'documentDate', attachment.document_date,
                  'amount', attachment.amount,
                  'currencyCode', COALESCE(attachment.currency_code, o.currency_code, 'CZK'),
                  'exchangeRate', CASE
                    WHEN COALESCE(attachment.currency_code, o.currency_code, 'CZK') = 'CZK' THEN 1
                    ELSE COALESCE(attachment.exchange_rate, 1)
                  END,
                  'amountCzk', COALESCE(
                    attachment.amount_czk,
                    attachment.amount * CASE
                      WHEN COALESCE(attachment.currency_code, o.currency_code, 'CZK') = 'CZK' THEN 1
                      ELSE COALESCE(attachment.exchange_rate, 1)
                    END
                  ),
                  'fileName', attachment.file_name,
                  'heliosExpenseCodeId', attachment.helios_expense_code_id,
                  'heliosExpenseCodeLabel', attachment.helios_expense_code_label,
                  'contentType', attachment.content_type,
                  'byteSize', attachment.byte_size,
                  'sha256', attachment.sha256,
                  'uploadedAt', attachment.uploaded_at,
                  'heliosExpenseCode', COALESCE(
                    attachment.helios_expense_code_id,
                    CASE attachment.expense_kind
                      WHEN 'lodging' THEN 1
                      WHEN 'fuel' THEN 2
                      WHEN 'parking' THEN 5
                      WHEN 'fare' THEN 6
                      WHEN 'meal' THEN 10
                      ELSE 17
                    END
                  )
                )
                ORDER BY attachment.uploaded_at
              )
              FROM travel.travel_attachment attachment
              WHERE attachment.travel_order_id = o.id
            ), '[]'::jsonb),
            'helios', jsonb_build_object(
              'zakazkaTable', 'TabZakazka',
              'headerTable', 'TabICestak',
              'routeLineTable', 'TabICestaUsek',
              'expenseTable', 'TabICestaNakl',
              'documentTables', jsonb_build_array('TabDokumenty', 'TabDokumVazba'),
              'zakazkaLookup', jsonb_build_object(
                'Rada', 'CPR',
                'CisloZakazky', o.order_no
              ),
              'zakazkaValues', jsonb_build_object(
                'Rada', 'CPR',
                'CisloZakazky', o.order_no,
                'Nazev', left(COALESCE(NULLIF(o.purpose, ''), o.order_no), 100),
                'DruhyNazev', '',
                'Stredisko', COALESCE(ep.cost_center_code, cost_center.code),
                'DatumStartPlan', o.planned_start_at,
                'DatumStartReal', o.planned_start_at,
                'DatumKonecPlan', o.planned_end_at,
                'DatumKonecReal', o.planned_end_at,
                'Ukonceno', 0,
                'Stav', '1',
                'Priorita', 'Normal',
                'Identifikator', '',
                'CisloObjednavky', '',
                'CisloNabidky', '',
                'CisloSmlouvy', '',
                'Upozorneni', '',
                'VynosPlan', 0,
                'JeProjekt', false,
                'JeServis', false,
                'VerejnaZakazka', false,
                'JeNovaVetaEditor', false,
                'AVAReferenceID', upper(o.id::text),
                'AVAExternalID', '',
                'AVAOutputFlag', 0,
                'Autor', 'CestovniPrikazy',
                'DatPorizeni', COALESCE(o.approved_at, o.updated_at)
              ),
              'headerValues', jsonb_build_object(
                'CisloZamestnance',
                  CASE WHEN ep.personal_number ~ '^[0-9]+$' THEN ep.personal_number::integer ELSE NULL END,
                'CisDok', o.order_no,
                'DatVystDokl', COALESCE(o.approved_at, o.updated_at),
                'Stav', 'O',
                'CilCesty', left(COALESCE(o.destination, o.purpose, ''), 60),
                'UcelCesty', o.purpose,
                'DatCasPocatek', o.planned_start_at,
                'DatCasKonec', o.planned_end_at,
                'CisloZakazky', o.order_no,
                'Stredisko', COALESCE(ep.cost_center_code, cost_center.code),
                'TypCesty',
                  CASE WHEN EXISTS (
                    SELECT 1 FROM travel.travel_route_line foreign_line
                    WHERE foreign_line.travel_order_id = o.id
                      AND foreign_line.segment_type = 'foreign'
                  ) THEN 'Z' ELSE 'T' END,
                'TypDopravy',
                  CASE
                    WHEN EXISTS (
                      SELECT 1 FROM travel.travel_route_line car_line
                      WHERE car_line.travel_order_id = o.id
                        AND car_line.transport_kind IN ('private_car', 'company_car')
                    ) THEN 'S'
                    WHEN EXISTS (
                      SELECT 1 FROM travel.travel_route_line public_line
                      WHERE public_line.travel_order_id = o.id
                        AND public_line.transport_kind = 'public_transport'
                    ) THEN 'V'
                    ELSE 'J'
                  END,
                'SPZ', COALESCE(total.calculation_snapshot #>> '{order,vehicle,plate}', ''),
                'Spotreba', NULLIF(total.calculation_snapshot #>> '{order,vehicle,consumption}', '')::numeric,
                'CenaL', NULLIF(total.calculation_snapshot #>> '{order,vehicle,fuelPrice}', '')::numeric,
                'SazbaKM', NULLIF(total.calculation_snapshot #>> '{order,vehicle,basicKmRate}', '')::numeric,
                'SDPlati', 'O',
                'ProcKapes', 0,
                'PHMZahrpo', 0,
                'PHMKc', COALESCE(total.calculation_snapshot #>> '{calculation,totalFuel}', '0')::numeric,
                'CelkemDiety', COALESCE(total.meal_amount, 0),
                'CelkemDietyZak', COALESCE(total.meal_amount, 0),
                'CelkemNaklady', COALESCE(total.lodging_amount, 0) + COALESCE(total.other_amount, 0),
                'CelkemNahrady',
                  COALESCE(NULLIF(total.calculation_snapshot #>> '{calculation,totalBasicKmComp}', '')::numeric, total.transport_amount, 0),
                'CelkemPHM', COALESCE(total.calculation_snapshot #>> '{calculation,totalFuel}', '0')::numeric,
                'CelkemKc', round(COALESCE(total.gross_amount, 0), 0),
                'CelkemKCZak', round(COALESCE(total.gross_amount, 0), 0),
                'CelkemKcPredZao', COALESCE(total.gross_amount, 0),
                'CelkemKcZakPredZao', COALESCE(total.gross_amount, 0),
                'KMCelkem', COALESCE(total.total_km, 0),
                'KMZahr', COALESCE((
                  SELECT sum(foreign_km.km)
                  FROM travel.travel_route_line foreign_km
                  WHERE foreign_km.travel_order_id = o.id
                    AND foreign_km.segment_type = 'foreign'
                ), 0),
                'VratkaTuz', true,
                'MenaPrepocet', o.currency_code,
                'KurzPrepocet', COALESCE(NULLIF(total.calculation_snapshot #>> '{order,trip,exchangeRate}', '')::numeric, 1),
                'FixKurz', false,
                'idrada', 15,
                'JeNovaVetaEditor', false,
                'CestakJakHledatKurz', 1,
                'ZpusobKurzu', 0,
                'CelkemPrepocet', COALESCE(total.gross_amount, 0)
              )
            ),
            'importable',
              COALESCE(ep.personal_number ~ '^[0-9]+$', false)
              AND ep.helios_employee_id IS NOT NULL
              AND ep.last_synced_at IS NOT NULL
              AND owner.helios_personal_number = ep.personal_number
              AND o.planned_start_at IS NOT NULL
              AND o.planned_end_at IS NOT NULL
              AND COALESCE(o.order_no, '') <> ''
              AND length(o.order_no) <= 15,
            'validation', jsonb_build_object(
              'missingPersonalNumber', ep.personal_number IS NULL OR ep.personal_number !~ '^[0-9]+$',
              'unverifiedPersonalNumber',
                NOT (
                  COALESCE(ep.personal_number ~ '^[0-9]+$', false)
                  AND ep.helios_employee_id IS NOT NULL
                  AND ep.last_synced_at IS NOT NULL
                  AND owner.helios_personal_number = ep.personal_number
              ),
              'missingPeriod', o.planned_start_at IS NULL OR o.planned_end_at IS NULL,
              'missingCostCenter', COALESCE(ep.cost_center_code, cost_center.code, '') = '',
              'missingOrderNumber', COALESCE(o.order_no, '') = '',
              'orderNumberTooLong', length(COALESCE(o.order_no, '')) > 15,
              'hasAttachments', EXISTS (
                SELECT 1 FROM travel.travel_attachment attachment_check
                WHERE attachment_check.travel_order_id = o.id
              )
            )
          ) AS item
        FROM candidates o
        JOIN travel.app_user owner ON owner.id = o.owner_user_id
        LEFT JOIN travel.employee_profile ep ON ep.id = o.employee_profile_id
        LEFT JOIN travel.cost_center cost_center ON cost_center.id = o.cost_center_id
        LEFT JOIN travel.travel_order_total total ON total.travel_order_id = o.id
        LEFT JOIN travel.vehicle used_vehicle
          ON used_vehicle.id = CASE
            WHEN (total.calculation_snapshot #>> '{order,vehicle,id}')
              ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
            THEN (total.calculation_snapshot #>> '{order,vehicle,id}')::uuid
            ELSE NULL::uuid
          END
      )
      SELECT jsonb_build_object(
        'generatedAt', now(),
        'count', count(*),
        'items', COALESCE(jsonb_agg(item ORDER BY sort_at DESC), '[]'::jsonb)
      )::text
      FROM items;
    """
    return jsonify(run_psql_json(sql, {"limit": limit}))


@app.post("/api/helios/import-results")
@require_helios_import_access
def helios_import_result():
    payload = request.get_json(silent=True) or {}
    import_id = valid_uuid(payload.get("importId") or payload.get("travelOrderId") or payload.get("id"))
    if not import_id:
        return jsonify({"error": "invalid_import_id"}), 400

    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    helios = payload.get("helios") if isinstance(payload.get("helios"), dict) else {}
    helios_document_id = str(
        payload.get("heliosTravelOrderId")
        or payload.get("heliosDocumentId")
        or payload.get("tabICestakId")
        or project.get("code")
        or helios.get("tabICestakId")
        or helios.get("travelOrderId")
        or ""
    ).strip()
    if not re.fullmatch(r"\d{1,20}", helios_document_id):
        return jsonify({"error": "invalid_helios_travel_order_id"}), 400

    vehicle = payload.get("vehicle") if isinstance(payload.get("vehicle"), dict) else {}
    helios_vehicle_id = str(
        payload.get("heliosVehicleId")
        or payload.get("tabIVozidloId")
        or vehicle.get("id")
        or helios.get("tabIVozidloId")
        or helios.get("vehicleId")
        or ""
    ).strip()
    if helios_vehicle_id and not re.fullmatch(r"\d{1,20}", helios_vehicle_id):
        return jsonify({"error": "invalid_helios_vehicle_id"}), 400

    order_no = str(payload.get("orderNo") or payload.get("cisDok") or "").strip()
    payload_json = json.dumps(payload, ensure_ascii=False)
    sql = """
      WITH target AS (
        SELECT
          o.id,
          o.order_no,
          o.status::text AS status,
          o.export_status::text AS export_status,
          o.helios_document_id,
          CASE
            WHEN (total.calculation_snapshot #>> '{order,vehicle,id}')
              ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
            THEN (total.calculation_snapshot #>> '{order,vehicle,id}')::uuid
            ELSE NULL::uuid
          END AS used_vehicle_id
        FROM travel.travel_order o
        LEFT JOIN travel.travel_order_total total ON total.travel_order_id = o.id
        WHERE o.id = :'import_id'::uuid
          AND (NULLIF(:'order_no', '') IS NULL OR o.order_no = :'order_no')
        FOR UPDATE OF o
      ),
      updated AS (
        UPDATE travel.travel_order o
        SET export_status = 'exported'::travel.export_status,
            helios_document_id = :'helios_document_id',
            helios_exported_at = now(),
            helios_export_payload = jsonb_build_object(
              'project', jsonb_build_object('code', :'helios_document_id'),
              'helios', jsonb_build_object(
                'table', 'TabICestak',
                'id', :'helios_document_id'
              ),
              'callbackPayload', NULLIF(:'payload_json', '')::jsonb
            )
        WHERE o.id = (SELECT id FROM target)
          AND (SELECT status FROM target) = 'approved'
          AND (
            (SELECT helios_document_id FROM target) IS NULL
            OR (SELECT helios_document_id FROM target) = :'helios_document_id'
          )
        RETURNING
          o.id,
          o.order_no,
          o.export_status::text AS export_status,
          o.helios_document_id,
          o.helios_exported_at
      ),
      vehicle_updated AS (
        UPDATE travel.vehicle vehicle
        SET helios_id = NULLIF(:'helios_vehicle_id', ''),
            source_system = CASE
              WHEN vehicle.source_system = 'local' THEN 'mixed'::travel.user_source
              ELSE vehicle.source_system
            END,
            helios_export_status = 'exported'::travel.export_status,
            helios_exported_at = now(),
            helios_export_failed_at = NULL,
            helios_export_error = NULL,
            updated_at = now()
        WHERE vehicle.id = (SELECT used_vehicle_id FROM target)
          AND EXISTS (SELECT 1 FROM updated)
          AND NULLIF(:'helios_vehicle_id', '') IS NOT NULL
        RETURNING
          vehicle.id,
          vehicle.helios_id,
          vehicle.helios_export_status::text AS helios_export_status
      )
      SELECT jsonb_build_object(
        'found', EXISTS (SELECT 1 FROM target),
        'updated', EXISTS (SELECT 1 FROM updated),
        'notApproved', EXISTS (
          SELECT 1 FROM target WHERE status <> 'approved'
        ),
        'conflictingHeliosDocument', EXISTS (
          SELECT 1
          FROM target
          WHERE helios_document_id IS NOT NULL
            AND helios_document_id <> :'helios_document_id'
        ),
        'travelOrderId', COALESCE(
          (SELECT id::text FROM updated),
          (SELECT id::text FROM target)
        ),
        'orderNo', COALESCE(
          (SELECT order_no FROM updated),
          (SELECT order_no FROM target)
        ),
        'exportStatus', COALESCE(
          (SELECT export_status FROM updated),
          (SELECT export_status FROM target)
        ),
        'heliosDocumentId', COALESCE(
          (SELECT helios_document_id FROM updated),
          (SELECT helios_document_id FROM target),
          :'helios_document_id'
        ),
        'project', jsonb_build_object('code', :'helios_document_id'),
        'vehicleUpdated', EXISTS (SELECT 1 FROM vehicle_updated),
        'vehicleId', (SELECT id::text FROM vehicle_updated),
        'heliosVehicleId', COALESCE((SELECT helios_id FROM vehicle_updated), NULLIF(:'helios_vehicle_id', '')),
        'heliosExportedAt', (SELECT helios_exported_at FROM updated)
      )::text;
    """
    result = run_psql_json(
        sql,
        {
            "import_id": import_id,
            "order_no": order_no,
            "helios_document_id": helios_document_id,
            "helios_vehicle_id": helios_vehicle_id,
            "payload_json": payload_json,
        },
    )
    if not result.get("found"):
        return jsonify({"error": "travel_order_not_found"}), 404
    if result.get("conflictingHeliosDocument"):
        return jsonify({"error": "travel_order_already_imported_elsewhere", **result}), 409
    if result.get("notApproved"):
        return jsonify({"error": "travel_order_not_approved", **result}), 409
    if not result.get("updated"):
        return jsonify({"error": "travel_order_not_updated", **result}), 409
    return jsonify(result)


@app.post("/api/helios/import-reset")
@require_helios_import_access
def helios_import_reset():
    payload = request.get_json(silent=True) or {}
    import_id = valid_uuid(payload.get("importId") or payload.get("travelOrderId") or payload.get("id"))
    if not import_id:
        return jsonify({"error": "invalid_import_id"}), 400

    order_no = str(payload.get("orderNo") or payload.get("cisDok") or "").strip()
    reset_vehicle = bool(payload.get("resetVehicle", True))
    sql = """
      WITH target AS (
        SELECT
          o.id,
          o.order_no,
          o.status::text AS status,
          o.export_status::text AS export_status,
          o.helios_document_id,
          CASE
            WHEN (total.calculation_snapshot #>> '{order,vehicle,id}')
              ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
            THEN (total.calculation_snapshot #>> '{order,vehicle,id}')::uuid
            ELSE NULL::uuid
          END AS used_vehicle_id
        FROM travel.travel_order o
        LEFT JOIN travel.travel_order_total total ON total.travel_order_id = o.id
        WHERE o.id = :'import_id'::uuid
          AND (NULLIF(:'order_no', '') IS NULL OR o.order_no = :'order_no')
        FOR UPDATE OF o
      ),
      order_reset AS (
        UPDATE travel.travel_order o
        SET export_status = 'ready'::travel.export_status,
            helios_document_id = NULL,
            helios_export_payload = NULL,
            helios_exported_at = NULL
        WHERE o.id = (SELECT id FROM target)
          AND (SELECT status FROM target) = 'approved'
        RETURNING o.id, o.order_no, o.export_status::text AS export_status
      ),
      vehicle_reset AS (
        UPDATE travel.vehicle vehicle
        SET helios_id = NULL,
            source_system = CASE
              WHEN vehicle.source_system = 'mixed' THEN 'local'::travel.user_source
              ELSE vehicle.source_system
            END,
            helios_export_status = 'queued'::travel.export_status,
            helios_export_requested_at = now(),
            helios_exported_at = NULL,
            helios_export_failed_at = NULL,
            helios_export_error = NULL,
            helios_export_travel_order_id = (SELECT id FROM target),
            updated_at = now()
        WHERE :'reset_vehicle'::boolean
          AND vehicle.id = (SELECT used_vehicle_id FROM target)
          AND EXISTS (SELECT 1 FROM order_reset)
          AND vehicle.source_system IN ('local'::travel.user_source, 'mixed'::travel.user_source)
        RETURNING vehicle.id, vehicle.helios_export_status::text AS helios_export_status
      )
      SELECT jsonb_build_object(
        'found', EXISTS (SELECT 1 FROM target),
        'reset', EXISTS (SELECT 1 FROM order_reset),
        'notApproved', EXISTS (SELECT 1 FROM target WHERE status <> 'approved'),
        'travelOrderId', COALESCE((SELECT id::text FROM order_reset), (SELECT id::text FROM target)),
        'orderNo', COALESCE((SELECT order_no FROM order_reset), (SELECT order_no FROM target)),
        'exportStatus', COALESCE((SELECT export_status FROM order_reset), (SELECT export_status FROM target)),
        'vehicleReset', EXISTS (SELECT 1 FROM vehicle_reset),
        'vehicleId', (SELECT id::text FROM vehicle_reset)
      )::text;
    """
    result = run_psql_json(
        sql,
        {
            "import_id": import_id,
            "order_no": order_no,
            "reset_vehicle": "true" if reset_vehicle else "false",
        },
    )
    if not result.get("found"):
        return jsonify({"error": "travel_order_not_found"}), 404
    if result.get("notApproved"):
        return jsonify({"error": "travel_order_not_approved", **result}), 409
    if not result.get("reset"):
        return jsonify({"error": "travel_order_not_reset", **result}), 409
    return jsonify(result)


@app.get("/api/rates/current")
@require_auth
def current_rates():
    target_date = str(request.args.get("date") or "").strip()
    rate = get_current_rate_set(target_date)
    if not rate:
        return jsonify({"error": "rate_set_not_found"}), 404
    return jsonify(rate)


@app.get("/api/rates/monitor")
@require_auth
def rate_monitor():
    return jsonify(build_rate_monitor_payload(update_db=False))


@app.post("/api/rates/monitor/check")
@require_role("admin")
def check_rate_monitor():
    return jsonify(build_rate_monitor_payload(update_db=True))


def get_current_rate_set(target_date: str = ""):
    sql = """
      WITH target AS (
        SELECT COALESCE(NULLIF(:'target_date', '')::date, CURRENT_DATE) AS value
      ),
      rs AS (
        SELECT rate_set.*
        FROM travel.legislation_rate_set rate_set, target
        WHERE rate_set.is_active
          AND rate_set.valid_from <= target.value
          AND (rate_set.valid_to IS NULL OR rate_set.valid_to >= target.value)
        ORDER BY rate_set.valid_from DESC
        LIMIT 1
      )
      SELECT to_jsonb(t)::text
      FROM (
        SELECT
          rs.id::text AS id,
          rs.code,
          rs.name,
          rs.valid_from AS "validFrom",
          rs.valid_to AS "validTo",
          rs.source_note AS "sourceNote",
          rs.regulation_no AS "regulationNo",
          rs.source_url AS "sourceUrl",
          rs.published_at AS "publishedAt",
          rs.checked_at AS "checkedAt",
          COALESCE((
            SELECT amount_per_km
            FROM travel.km_compensation_rate km
            WHERE km.rate_set_id = rs.id
              AND km.vehicle_kind = 'passenger_car'
            LIMIT 1
          ), 0) AS "basicKmRate",
          COALESCE((
            SELECT jsonb_object_agg(fuel.fuel_type::text, fuel.price_per_unit ORDER BY fuel.fuel_type::text)
            FROM travel.fuel_price_rate fuel
            WHERE fuel.rate_set_id = rs.id
          ), '{}'::jsonb) AS "fuelPrices",
          COALESCE((
            SELECT jsonb_agg(
              jsonb_build_object(
                'key', meal.band_code,
                'label', CASE meal.band_code
                  WHEN '5_12' THEN '5 až 12 hodin'
                  WHEN '12_18' THEN 'nad 12 až 18 hodin'
                  WHEN '18_plus' THEN 'nad 18 hodin'
                  ELSE meal.band_code
                END,
                'min', meal.hours_from,
                'max', meal.hours_to,
                'amount', meal.amount,
                'reductionPct', meal.reduction_percent_per_free_meal
              )
              ORDER BY meal.hours_from
            )
            FROM travel.domestic_meal_rate meal
            WHERE meal.rate_set_id = rs.id
          ), '[]'::jsonb) AS "mealBands"
        FROM rs
      ) t;
    """
    return run_psql_json(sql, {"target_date": target_date})


def build_rate_monitor_payload(update_db: bool = False):
    monitor_sql = """
      SELECT to_jsonb(t)::text
      FROM (
        SELECT
          id::text,
          monitor_code AS "monitorCode",
          name,
          source_url AS "sourceUrl",
          latest_known_regulation_no AS "latestKnownRegulationNo",
          latest_known_valid_from AS "latestKnownValidFrom",
          latest_known_payload AS "latestKnownPayload",
          status,
          message,
          last_checked_at AS "lastCheckedAt",
          next_check_after AS "nextCheckAfter",
          updated_at AS "updatedAt"
        FROM travel.legislation_rate_monitor
        WHERE monitor_code = 'CZ_TRAVEL_RATES'
        LIMIT 1
      ) t;
    """
    monitor = run_psql_json(monitor_sql) or {}
    rate = get_current_rate_set("")
    effective_status, effective_message = compare_rate_set_to_monitor(rate, monitor)

    if update_db and monitor:
        update_sql = """
          WITH updated AS (
            UPDATE travel.legislation_rate_monitor
            SET status = :'status',
                message = :'message',
                last_checked_at = now()
            WHERE monitor_code = 'CZ_TRAVEL_RATES'
            RETURNING id
          )
          SELECT jsonb_build_object('updated_count', count(*))::text FROM updated;
        """
        run_psql_json(update_sql, {"status": effective_status, "message": effective_message})
        monitor = run_psql_json(monitor_sql) or monitor

    return {
        "monitor": {
            **monitor,
            "effectiveStatus": effective_status,
            "effectiveMessage": effective_message,
        },
        "rate": rate,
    }


def compare_rate_set_to_monitor(rate: dict | None, monitor: dict | None) -> tuple[str, str]:
    if not monitor:
        return "unknown", "Monitor sazeb nenĂ­ inicializovanĂ˝."
    if not rate:
        return "missing", "Pro dneĹˇnĂ­ datum nenĂ­ v databĂˇzi aktivnĂ­ sada sazeb."

    expected = monitor.get("latestKnownPayload") or {}
    expected_prices = expected.get("fuelPrices") or {}
    current_prices = rate.get("fuelPrices") or {}
    mismatches: list[str] = []

    expected_basic = number_like(expected.get("basicKmRate"))
    current_basic = number_like(rate.get("basicKmRate"))
    if float(expected_basic) and round(float(expected_basic), 2) != round(float(current_basic), 2):
        mismatches.append("zĂˇkladnĂ­ nĂˇhrada KÄŤ/km")

    for fuel_type, expected_price in expected_prices.items():
        current_price = current_prices.get(fuel_type)
        if round(float(number_like(expected_price)), 2) != round(float(number_like(current_price)), 2):
            mismatches.append(f"PHM {fuel_type}")

    valid_from = str(rate.get("validFrom") or "")
    expected_valid_from = str(monitor.get("latestKnownValidFrom") or "")
    if expected_valid_from and valid_from < expected_valid_from:
        mismatches.append("účinnost sazeb")

    if mismatches:
        return (
            "out_of_date",
            "Lokální sazby se liší od poslední známé vyhlášky: " + ", ".join(mismatches) + ".",
        )

    source = str(monitor.get("latestKnownRegulationNo") or rate.get("regulationNo") or "aktuální vyhláška").rstrip(".")
    return "ok", f"Lokální sazby odpovídají poslední známé vyhlášce {source}."


@app.get("/api/admin/users/options")
@require_role("admin")
def admin_user_options():
    sql = """
      SELECT jsonb_build_object(
        'roles', (SELECT jsonb_agg(to_jsonb(r) ORDER BY code) FROM (
          SELECT code, name, description FROM travel.role
        ) r),
        'transportKinds', jsonb_build_array(
          jsonb_build_object('code', 'private_car', 'name', 'VlastnĂ­ vozidlo'),
          jsonb_build_object('code', 'company_car', 'name', 'SluĹľebnĂ­ vozidlo'),
          jsonb_build_object('code', 'public_transport', 'name', 'VeĹ™ejnĂˇ doprava'),
          jsonb_build_object('code', 'taxi', 'name', 'Taxi'),
          jsonb_build_object('code', 'plane', 'name', 'Letadlo'),
          jsonb_build_object('code', 'other', 'name', 'JinĂ©')
        ),
        'fuelTypes', jsonb_build_array(
          jsonb_build_object('code', 'ba95', 'name', 'Benzin 95'),
          jsonb_build_object('code', 'ba98', 'name', 'Benzin 98'),
          jsonb_build_object('code', 'diesel', 'name', 'Nafta'),
          jsonb_build_object('code', 'electricity', 'name', 'ElektĹ™ina'),
          jsonb_build_object('code', 'other', 'name', 'JinĂ©')
        ),
        'approvers', COALESCE((SELECT jsonb_agg(to_jsonb(a) ORDER BY display_name) FROM (
          SELECT DISTINCT
            u.id::text AS id,
            u.display_name,
            u.email::text AS email,
            u.login_name::text AS login_name
          FROM travel.app_user u
          JOIN travel.user_role ur ON ur.user_id = u.id
          JOIN travel.role r ON r.id = ur.role_id AND r.code = 'approver'
          WHERE u.is_active
        ) a), '[]'::jsonb)
      )::text;
    """
    return jsonify(run_psql_json(sql))


@app.get("/api/admin/users")
@require_role("admin")
def admin_users():
    sql = """
      SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.display_name), '[]'::jsonb)::text
      FROM (
        SELECT
          u.id::text AS id,
          u.login_name::text AS login_name,
          u.email::text AS email,
          u.display_name,
          u.is_active,
          u.source_system,
          u.helios_user_id,
          ep.id::text AS employee_profile_id,
          ep.personal_number,
          ep.address,
          ep.phone,
          ep.organization_name,
          COALESCE(to_char(ep.work_start, 'HH24:MI'), '08:00') AS work_start,
          COALESCE(to_char(ep.work_end, 'HH24:MI'), '16:30') AS work_end,
          ep.cost_center_code,
          ep.cost_center_name,
          ep.department_name,
          COALESCE(ep.default_transport_kind::text, 'private_car') AS default_transport_kind,
          ep.default_approver_user_id::text,
          approver.display_name AS default_approver_name,
          COALESCE((
            SELECT jsonb_agg(to_jsonb(approver_option) ORDER BY approver_option.is_default DESC, approver_option.name)
            FROM (
              SELECT
                option.approver_user_id::text AS id,
                option_user.display_name AS name,
                option_user.email::text AS email,
                option_user.login_name::text AS login,
                option.is_default
              FROM travel.employee_approver_option option
              JOIN travel.app_user option_user ON option_user.id = option.approver_user_id
              WHERE option.employee_profile_id = ep.id
                AND option.is_active
                AND option_user.id <> u.id
            ) approver_option
          ), '[]'::jsonb) AS approver_options,
          ep.manager_user_id::text,
          manager.display_name AS manager_name,
          ep.accountant_user_id::text,
          accountant.display_name AS accountant_name,
          dv.id::text AS default_vehicle_id,
          dv.brand AS vehicle_brand,
          dv.plate AS vehicle_plate,
          dv.engine_volume_cc AS vehicle_engine_volume,
          COALESCE(dv.fuel_type::text, 'ba95') AS vehicle_fuel_type,
          COALESCE(dv.consumption_l_per_100km, 0) AS vehicle_consumption,
          COALESCE(dv.secondary_fuel_type::text, '') AS vehicle_secondary_fuel_type,
          COALESCE(dv.secondary_consumption_per_100km, 0) AS vehicle_secondary_consumption,
          COALESCE((
            SELECT jsonb_agg(to_jsonb(vehicle_list) ORDER BY vehicle_list.is_default DESC, vehicle_list.brand, vehicle_list.plate)
            FROM (
              SELECT
                vehicle.id::text AS id,
                COALESCE(vehicle.brand, '') AS brand,
                COALESCE(vehicle.plate, '') AS plate,
                COALESCE(vehicle.engine_volume_cc::text, '') AS engine_volume,
                COALESCE(vehicle.fuel_type::text, 'ba95') AS fuel_type,
                COALESCE(vehicle.consumption_l_per_100km, 0) AS consumption,
                COALESCE(vehicle.secondary_fuel_type::text, '') AS secondary_fuel_type,
                COALESCE(vehicle.secondary_consumption_per_100km, 0) AS secondary_consumption,
                COALESCE(vehicle.helios_id, '') AS helios_id,
                COALESCE(vehicle.source_system::text, 'local') AS source_system,
                COALESCE(vehicle.helios_export_status::text, 'not_ready') AS helios_export_status,
                vehicle.helios_export_requested_at,
                vehicle.helios_exported_at,
                vehicle.helios_export_error,
                COALESCE((
                  SELECT jsonb_agg(to_jsonb(document_row) ORDER BY document_row."uploadedAt")
                  FROM (
                    SELECT
                      document.id::text AS id,
                      document.client_document_id AS "clientDocumentId",
                      document.document_kind AS "documentKind",
                      document.file_name AS "fileName",
                      document.content_type AS "contentType",
                      document.byte_size AS "byteSize",
                      document.sha256,
                      document.uploaded_at AS "uploadedAt"
                    FROM travel.vehicle_document document
                    WHERE document.vehicle_id = vehicle.id
                  ) document_row
                ), '[]'::jsonb) AS documents,
                vehicle.is_default,
                vehicle.is_private
              FROM travel.vehicle vehicle
              WHERE vehicle.owner_user_id = u.id
                AND vehicle.is_active
            ) vehicle_list
          ), '[]'::jsonb) AS vehicles,
          COALESCE((
            SELECT array_agg(r.code ORDER BY r.code)
            FROM travel.user_role ur
            JOIN travel.role r ON r.id = ur.role_id
            WHERE ur.user_id = u.id
          ), ARRAY[]::text[]) AS roles
        FROM travel.app_user u
        LEFT JOIN travel.employee_profile ep ON ep.user_id = u.id
        LEFT JOIN travel.app_user approver ON approver.id = ep.default_approver_user_id
        LEFT JOIN travel.app_user manager ON manager.id = ep.manager_user_id
        LEFT JOIN travel.app_user accountant ON accountant.id = ep.accountant_user_id
        LEFT JOIN LATERAL (
          SELECT vehicle.*
          FROM travel.vehicle vehicle
          WHERE vehicle.owner_user_id = u.id
            AND vehicle.is_active
          ORDER BY (vehicle.id = ep.default_vehicle_id) DESC, vehicle.is_default DESC, vehicle.created_at DESC
          LIMIT 1
        ) dv ON true
      ) t;
    """
    return jsonify({"users": run_psql_json(sql)})


@app.post("/api/admin/users")
@require_role("admin")
def admin_create_user():
    payload = request.get_json(silent=True) or {}
    return save_admin_user(payload)


@app.put("/api/admin/users/<user_id>")
@require_role("admin")
def admin_update_user(user_id):
    payload = request.get_json(silent=True) or {}
    payload["id"] = user_id
    return save_admin_user(payload)


@app.delete("/api/admin/users/<user_id>")
@require_role("admin")
def admin_delete_user(user_id):
    actor_user_id = str((request.current_user or {}).get("user_id") or "")
    if not user_id:
        return jsonify({"error": "missing_user_id"}), 400
    if actor_user_id and actor_user_id == user_id:
        return jsonify({"error": "cannot_delete_self"}), 400

    sql = """
      WITH target AS (
        SELECT id, source_system::text AS source_system, helios_user_id
        FROM travel.app_user
        WHERE id = NULLIF(:'user_id', '')::uuid
      ),
      blocked_target AS (
        SELECT id
        FROM target
        WHERE source_system IN ('helios', 'mixed')
           OR helios_user_id IS NOT NULL
      ),
      revoked_sessions AS (
        UPDATE travel.auth_session
        SET revoked_at = now()
        WHERE user_id = (SELECT id FROM target)
          AND NOT EXISTS (SELECT 1 FROM blocked_target)
          AND revoked_at IS NULL
        RETURNING id
      ),
      deleted_identity AS (
        DELETE FROM travel.local_auth_identity
        WHERE user_id = (SELECT id FROM target)
          AND NOT EXISTS (SELECT 1 FROM blocked_target)
        RETURNING user_id
      ),
      deleted_user AS (
        DELETE FROM travel.app_user
        WHERE id = (SELECT id FROM target)
          AND NOT EXISTS (SELECT 1 FROM blocked_target)
        RETURNING id
      )
      SELECT to_jsonb(t)::text
      FROM (
        SELECT
          (SELECT count(*) FROM target) AS found_count,
          (SELECT count(*) FROM blocked_target) AS blocked_count,
          (SELECT count(*) FROM revoked_sessions) AS revoked_session_count,
          (SELECT count(*) FROM deleted_identity) AS deleted_identity_count,
          (SELECT count(*) FROM deleted_user) AS deleted_user_count
      ) t;
    """
    result = run_psql_json(sql, {"user_id": user_id}) or {}
    if int(result.get("found_count") or 0) == 0:
        return jsonify({"error": "user_not_found"}), 404
    if int(result.get("blocked_count") or 0) > 0:
        return jsonify({"error": "erp_managed_user"}), 409
    if int(result.get("deleted_user_count") or 0) == 0:
        return jsonify({"error": "delete_failed"}), 409
    return jsonify({"ok": True, "deleted_user_id": user_id})


def save_admin_user(payload: dict):
    user_id = payload.get("id")
    login_name = str(payload.get("login_name") or payload.get("login") or "").strip()
    display_name = str(payload.get("display_name") or "").strip()
    email = str(payload.get("email") or "").strip() or None
    password = str(payload.get("password") or "")
    roles = payload.get("roles") or ["employee"]
    is_active = bool(payload.get("is_active", True))
    personal_number = str(payload.get("personal_number") or "").strip()
    default_transport_kind = str(payload.get("default_transport_kind") or "private_car")
    vehicles = normalize_vehicles(payload)
    approver_options = normalize_approver_options(payload)

    if default_transport_kind not in TRANSPORT_KINDS:
        default_transport_kind = "private_car"

    if not login_name or not display_name:
        return jsonify({"error": "missing_required_fields"}), 400
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"error": "invalid_email"}), 400

    identity_conflict = find_user_identity_conflict(login_name, email or "", user_id or "")
    if identity_conflict:
        return jsonify({"error": identity_conflict["error"]}), 409
    if personal_number and find_personal_number_conflict(personal_number, user_id or ""):
        return jsonify({"error": "personal_number_exists"}), 409

    sql = """
      WITH requested_user AS (
        SELECT NULLIF(:'user_id', '')::uuid AS id
      ),
      updated_user AS (
        UPDATE travel.app_user u
        SET login_name = :'login_name'::citext,
            email = NULLIF(:'email', '')::citext,
            display_name = :'display_name',
            is_active = :'is_active'::boolean,
            source_system = CASE
              WHEN u.source_system = 'helios' THEN 'mixed'::travel.user_source
              ELSE u.source_system
            END
        WHERE u.id = (SELECT id FROM requested_user)
        RETURNING u.id
      ),
      inserted_user AS (
        INSERT INTO travel.app_user(login_name, email, display_name, is_active, source_system)
        SELECT :'login_name'::citext,
               NULLIF(:'email', '')::citext,
               :'display_name',
               :'is_active'::boolean,
               'local'
        WHERE NOT EXISTS (SELECT 1 FROM updated_user)
        ON CONFLICT (login_name) DO UPDATE
        SET email = EXCLUDED.email,
            display_name = EXCLUDED.display_name,
            is_active = EXCLUDED.is_active,
            source_system = CASE
              WHEN travel.app_user.source_system = 'helios' THEN 'mixed'::travel.user_source
              ELSE travel.app_user.source_system
            END
        RETURNING id
      ),
      saved_user AS (
        SELECT id FROM updated_user
        UNION ALL
        SELECT id FROM inserted_user
      ),
      removed_roles AS (
        DELETE FROM travel.user_role
        WHERE user_id = (SELECT id FROM saved_user)
        RETURNING user_id
      ),
      added_roles AS (
        INSERT INTO travel.user_role(user_id, role_id, assigned_by)
        SELECT (SELECT id FROM saved_user), r.id, :'actor_user_id'::uuid
        FROM travel.role r
        JOIN jsonb_array_elements_text(:'roles'::jsonb) wanted(code) ON wanted.code = r.code
        ON CONFLICT DO NOTHING
        RETURNING user_id
      ),
      saved_profile AS (
        INSERT INTO travel.employee_profile(
          user_id,
          personal_number,
          display_name,
          email,
          address,
          phone,
          organization_name,
          work_start,
          work_end,
          cost_center_code,
          cost_center_name,
          department_name,
          default_transport_kind,
          default_approver_user_id,
          manager_user_id,
          accountant_user_id,
          is_active
        )
        VALUES (
          (SELECT id FROM saved_user),
          NULLIF(:'personal_number', ''),
          :'display_name',
          NULLIF(:'email', '')::citext,
          NULLIF(:'address', ''),
          NULLIF(:'phone', ''),
          NULLIF(:'organization_name', ''),
          COALESCE(NULLIF(:'work_start', '')::time, '08:00'::time),
          COALESCE(NULLIF(:'work_end', '')::time, '16:30'::time),
          NULLIF(:'cost_center_code', ''),
          NULLIF(:'cost_center_name', ''),
          NULLIF(:'department_name', ''),
          :'default_transport_kind'::travel.transport_kind,
          NULLIF(:'default_approver_user_id', '')::uuid,
          NULLIF(:'manager_user_id', '')::uuid,
          NULLIF(:'accountant_user_id', '')::uuid,
          :'is_active'::boolean
        )
        ON CONFLICT (user_id) DO UPDATE
        SET personal_number = EXCLUDED.personal_number,
            display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            address = EXCLUDED.address,
            phone = EXCLUDED.phone,
            organization_name = EXCLUDED.organization_name,
            work_start = EXCLUDED.work_start,
            work_end = EXCLUDED.work_end,
            cost_center_code = EXCLUDED.cost_center_code,
            cost_center_name = EXCLUDED.cost_center_name,
            department_name = EXCLUDED.department_name,
            default_transport_kind = EXCLUDED.default_transport_kind,
            default_approver_user_id = EXCLUDED.default_approver_user_id,
            manager_user_id = EXCLUDED.manager_user_id,
            accountant_user_id = EXCLUDED.accountant_user_id,
            is_active = EXCLUDED.is_active
        RETURNING id
      ),
      saved_password AS (
        INSERT INTO travel.local_auth_identity(user_id, password_hash, password_login_enabled)
        SELECT (SELECT id FROM saved_user), crypt(:'password', gen_salt('bf', 12)), true
        WHERE NULLIF(:'password', '') IS NOT NULL
        ON CONFLICT (user_id) DO UPDATE
        SET password_hash = EXCLUDED.password_hash,
            password_changed_at = now(),
            password_login_enabled = true,
            failed_attempts = 0,
            locked_until = NULL
        RETURNING user_id
      )
      SELECT to_jsonb(t)::text
      FROM (
        SELECT
          u.id::text AS id,
          u.login_name::text AS login_name,
          u.email::text AS email,
          u.display_name,
          (SELECT id::text FROM saved_profile) AS employee_profile_id,
          (SELECT count(*) FROM removed_roles) AS removed_role_count,
          (SELECT count(*) FROM added_roles) AS added_role_count,
          (SELECT count(*) FROM saved_password) AS password_update_count
        FROM travel.app_user u
        WHERE u.id = (SELECT id FROM saved_user)
      ) t;
    """
    result = run_psql_json(
        sql,
        {
            "user_id": user_id or "",
            "login_name": login_name,
            "email": email or "",
            "display_name": display_name,
            "is_active": "true" if is_active else "false",
            "roles": json.dumps(roles),
            "actor_user_id": request.current_user["user_id"],
            "personal_number": personal_number,
            "address": payload.get("address") or "",
            "phone": payload.get("phone") or "",
            "organization_name": payload.get("organization_name") or "",
            "work_start": payload.get("work_start") or "",
            "work_end": payload.get("work_end") or "",
            "cost_center_code": payload.get("cost_center_code") or "",
            "cost_center_name": payload.get("cost_center_name") or "",
            "department_name": payload.get("department_name") or "",
            "default_transport_kind": default_transport_kind,
            "default_approver_user_id": payload.get("default_approver_user_id") or "",
            "manager_user_id": payload.get("manager_user_id") or "",
            "accountant_user_id": payload.get("accountant_user_id") or "",
            "password": password,
        },
    )
    result["vehicle_sync"] = save_user_vehicles(result["id"], vehicles)
    result["approver_sync"] = save_employee_approver_options(
        result["employee_profile_id"],
        approver_options,
        payload.get("default_approver_user_id") or "",
    )
    return jsonify({"user": result})


def route_line_number(value) -> float:
    try:
        return float(number_like(value))
    except (TypeError, ValueError):
        return 0.0


def route_line_has_business_content(line: dict, line_calc: dict) -> bool:
    text_keys = ("from", "to", "company", "purpose")
    if any(str(line.get(key) or "").strip() for key in text_keys):
        return True
    numeric_values = [
        line.get("km"),
        line.get("fare"),
        line.get("lodging"),
        line.get("other"),
        line.get("freeMeals"),
        line_calc.get("hours"),
        line_calc.get("meal"),
        line_calc.get("privateComp"),
        line_calc.get("total"),
    ]
    return any(route_line_number(value) != 0 for value in numeric_values)


def parse_route_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.replace(second=0, microsecond=0)


def validate_trip_dates_against_route_lines(trip: dict, lines: list[dict]) -> tuple[str, dict]:
    header_start = parse_route_datetime((trip or {}).get("startAt"))
    header_end = parse_route_datetime((trip or {}).get("endAt"))
    if header_start is None or header_end is None:
        return "missing_trip_dates", {}
    if header_end < header_start:
        return "trip_dates_invalid_range", {}

    first_start = None
    first_start_text = ""
    last_end = None
    last_end_text = ""
    for index, line in enumerate(lines):
        start_text = str(line.get("startAt") or "").strip()
        end_text = str(line.get("endAt") or "").strip()
        start_at = parse_route_datetime(start_text)
        end_at = parse_route_datetime(end_text)
        if start_at is None or end_at is None:
            return "route_line_invalid_dates", {"line": index + 1}
        if end_at < start_at:
            return "route_line_invalid_range", {"line": index + 1}
        if first_start is None or start_at < first_start:
            first_start = start_at
            first_start_text = start_text
        if last_end is None or end_at > last_end:
            last_end = end_at
            last_end_text = end_text

    if header_start != first_start or header_end != last_end:
        return "trip_dates_mismatch", {
            "expectedStartAt": first_start_text,
            "expectedEndAt": last_end_text,
            "actualStartAt": (trip or {}).get("startAt") or "",
            "actualEndAt": (trip or {}).get("endAt") or "",
        }
    return "", {}


def validate_submit_business_fields(trip: dict, lines: list[dict]) -> tuple[str, dict]:
    trip_purpose = str((trip or {}).get("purpose") or "").strip()
    if not trip_purpose:
        return "missing_trip_purpose", {}

    has_complete_route = False
    for index, line in enumerate(lines):
        from_place = str(line.get("from") or "").strip()
        to_place = str(line.get("to") or "").strip()
        if not from_place or not to_place:
            return "route_line_missing_places", {"line": index + 1}
        line_purpose = str(line.get("purpose") or "").strip()
        if not line_purpose:
            return "route_line_missing_purpose", {"line": index + 1}
        has_complete_route = True

    if not has_complete_route:
        return "missing_route_lines", {}
    return "", {}


def normalize_route_lines_for_submit(order: dict, calc: dict) -> tuple[list[dict], list[dict], str, int | None]:
    raw_lines = order.get("routeLines") if isinstance(order.get("routeLines"), list) else []
    raw_calc_lines = calc.get("lines") if isinstance(calc.get("lines"), list) else []
    lines: list[dict] = []
    calc_lines: list[dict] = []

    for index, raw_line in enumerate(raw_lines):
        if not isinstance(raw_line, dict):
            continue
        line = raw_line
        line_calc = raw_calc_lines[index] if index < len(raw_calc_lines) and isinstance(raw_calc_lines[index], dict) else {}
        start_at = str(line.get("startAt") or "").strip()
        end_at = str(line.get("endAt") or "").strip()
        has_content = route_line_has_business_content(line, line_calc)

        if not has_content and start_at and not end_at:
            continue
        if not has_content and not start_at and not end_at:
            continue
        if not start_at or not end_at:
            return [], [], "route_line_missing_dates", index + 1
        if str(line.get("segmentType") or line.get("segment_type") or "domestic") == "foreign" and not str(line.get("countryCode") or "").strip():
            return [], [], "route_line_missing_foreign_country", index + 1

        lines.append(line)
        calc_lines.append(line_calc)

    if not lines:
        return [], [], "missing_route_lines", None

    return lines, calc_lines, "", None


@app.post("/api/travel-orders/submit")
@require_auth
def submit_travel_order():
    payload = request.get_json(silent=True) or {}
    order = payload.get("order") or {}
    calc = payload.get("calculation") or {}
    order_no = str(order.get("number") or "").strip()
    if not order_no:
        return jsonify({"error": "missing_order_number"}), 400
    existing_order_id = valid_uuid(order.get("serverId") or order.get("travelOrderId") or "")
    order_no = ensure_unique_order_number(order_no, existing_order_id)
    travel_request_id = valid_uuid(order.get("travelRequestId") or "")
    if not travel_request_id:
        return jsonify({"error": "missing_travel_request"}), 400

    request_check_sql = """
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT id::text AS id
        FROM travel.travel_request
        WHERE id = :'request_id'::uuid
          AND owner_user_id = :'owner_user_id'::uuid
          AND status = 'approved'
        LIMIT 1
      ) t;
    """
    request_check = run_psql_json(
        request_check_sql,
        {
            "request_id": travel_request_id,
            "owner_user_id": request.current_user["user_id"],
        },
    )
    if not request_check or not request_check.get("id"):
        return jsonify({"error": "travel_request_not_approved"}), 400

    trip = order.get("trip") or {}
    approval = order.get("approval") or {}
    requested_approver_user_id = valid_uuid(approval.get("approverUserId"))
    if approval.get("approverUserId") and not requested_approver_user_id:
        return jsonify({"error": "invalid_approver"}), 400
    selected_approver_user_id, approver_error = resolve_order_approver(
        request.current_user["user_id"],
        requested_approver_user_id,
    )
    if approver_error:
        return jsonify({"error": approver_error}), 400
    accountant_check = run_psql_json(
        """
        SELECT to_jsonb(t)::text
        FROM (
          SELECT count(*) AS count
          FROM travel.app_user u
          JOIN travel.user_role ur ON ur.user_id = u.id
          JOIN travel.role r ON r.id = ur.role_id
          WHERE r.code = 'accountant'
            AND u.is_active
            AND u.id <> :'owner_user_id'::uuid
        ) t;
        """,
        {"owner_user_id": request.current_user["user_id"]},
    ) or {"count": 0}
    if int(accountant_check.get("count") or 0) == 0:
        return jsonify({"error": "no_accountant_available"}), 400

    lines, calc_lines, route_error, route_error_index = normalize_route_lines_for_submit(order, calc)
    if route_error:
        response = {"error": route_error}
        if route_error_index is not None:
            response["line"] = route_error_index
        return jsonify(response), 400
    trip_dates_error, trip_dates_payload = validate_trip_dates_against_route_lines(trip, lines)
    if trip_dates_error:
        return jsonify({"error": trip_dates_error, **trip_dates_payload}), 400
    business_error, business_payload = validate_submit_business_fields(trip, lines)
    if business_error:
        return jsonify({"error": business_error, **business_payload}), 400

    order_for_save = {**order, "routeLines": lines}
    sql = """
      WITH selected_approver AS (
        SELECT :'selected_approver_user_id'::uuid AS approver_user_id
      ),
      rate AS (
        SELECT id FROM travel.legislation_rate_set WHERE code = 'CZ-2026' LIMIT 1
      ),
      saved_order AS (
        INSERT INTO travel.travel_order(
          order_no,
          owner_user_id,
          employee_profile_id,
          travel_request_id,
          status,
          purpose,
          destination,
          visited_companies,
          companions,
          planned_start_at,
          planned_end_at,
          report_date,
          expected_expense,
          advance_amount,
          currency_code,
          rate_set_id,
          current_approver_user_id,
          final_approver_user_id,
          submitted_at,
          export_status
        )
        VALUES (
          :'order_no',
          :'owner_user_id'::uuid,
          (SELECT id FROM travel.employee_profile WHERE user_id = :'owner_user_id'::uuid LIMIT 1),
          :'travel_request_id'::uuid,
          'submitted',
          NULLIF(:'purpose', ''),
          NULLIF(:'destination', ''),
          NULLIF(:'visited_companies', ''),
          NULLIF(:'companions', ''),
          NULLIF(:'planned_start_at', '')::timestamptz,
          NULLIF(:'planned_end_at', '')::timestamptz,
          NULLIF(:'report_date', '')::date,
          :'expected_expense'::numeric,
          :'advance_amount'::numeric,
          :'currency_code',
          (SELECT id FROM rate),
          NULL,
          (SELECT approver_user_id FROM selected_approver),
          now(),
          'not_ready'
        )
        ON CONFLICT (order_no) DO UPDATE
        SET status = 'submitted',
            purpose = EXCLUDED.purpose,
            destination = EXCLUDED.destination,
            visited_companies = EXCLUDED.visited_companies,
            companions = EXCLUDED.companions,
            planned_start_at = EXCLUDED.planned_start_at,
            planned_end_at = EXCLUDED.planned_end_at,
            report_date = EXCLUDED.report_date,
            expected_expense = EXCLUDED.expected_expense,
            advance_amount = EXCLUDED.advance_amount,
            currency_code = EXCLUDED.currency_code,
            travel_request_id = EXCLUDED.travel_request_id,
            current_approver_user_id = EXCLUDED.current_approver_user_id,
            final_approver_user_id = EXCLUDED.final_approver_user_id,
            submitted_at = now(),
            approved_at = NULL,
            rejected_at = NULL,
            export_status = 'not_ready'::travel.export_status,
            helios_document_id = NULL,
            helios_export_payload = NULL,
            helios_exported_at = NULL
        RETURNING id, order_no, final_approver_user_id
      ),
      existing_lines AS (
        SELECT count(*) AS existing_count
        FROM travel.travel_route_line
        WHERE travel_order_id = (SELECT id FROM saved_order)
      ),
      inserted_lines AS (
        INSERT INTO travel.travel_route_line(
          travel_order_id,
          sequence_no,
          start_at,
          from_place,
          to_place,
          end_at,
          company_or_place,
          purpose,
          segment_type,
          foreign_country_code,
          foreign_country_name,
          foreign_meal_currency,
          foreign_meal_rate,
          foreign_exchange_rate,
          foreign_exchange_rate_date,
          foreign_meal_amount_czk,
          transport_kind,
          km,
          fare_amount,
          lodging_amount,
          other_amount,
          free_meals,
          calculated_hours,
          calculated_meal_amount,
          calculated_private_vehicle_amount,
          calculated_total_amount,
          calculation_detail
        )
        SELECT
          (SELECT id FROM saved_order),
          row_number() OVER (),
          NULLIF(line.start_at, '')::timestamptz,
          NULLIF(line.from_place, ''),
          NULLIF(line.to_place, ''),
          NULLIF(line.end_at, '')::timestamptz,
          NULLIF(line.company_or_place, ''),
          NULLIF(line.purpose, ''),
          COALESCE(NULLIF(line.segment_type, '')::travel.route_segment_type, 'domestic'),
          NULLIF(line.foreign_country_code, ''),
          NULLIF(line.foreign_country_name, ''),
          NULLIF(line.foreign_meal_currency, ''),
          COALESCE(line.foreign_meal_rate, 0),
          COALESCE(line.foreign_exchange_rate, 1),
          NULLIF(line.foreign_exchange_rate_date, '')::date,
          COALESCE(line.foreign_meal_amount_czk, 0),
          COALESCE(NULLIF(line.transport_kind, '')::travel.transport_kind, 'private_car'),
          COALESCE(line.km, 0),
          COALESCE(line.fare_amount, 0),
          COALESCE(line.lodging_amount, 0),
          COALESCE(line.other_amount, 0),
          COALESCE(line.free_meals, 0),
          COALESCE(line.calculated_hours, 0),
          COALESCE(line.calculated_meal_amount, 0),
          COALESCE(line.calculated_private_vehicle_amount, 0),
          COALESCE(line.calculated_total_amount, 0),
          COALESCE(line.calculation_detail, '{}'::jsonb)
        FROM jsonb_to_recordset(:'lines'::jsonb) AS line(
          start_at text,
          from_place text,
          to_place text,
          end_at text,
          company_or_place text,
          purpose text,
          segment_type text,
          foreign_country_code text,
          foreign_country_name text,
          foreign_meal_currency text,
          foreign_meal_rate numeric,
          foreign_exchange_rate numeric,
          foreign_exchange_rate_date text,
          foreign_meal_amount_czk numeric,
          transport_kind text,
          km numeric,
          fare_amount numeric,
          lodging_amount numeric,
          other_amount numeric,
          free_meals integer,
          calculated_hours numeric,
          calculated_meal_amount numeric,
          calculated_private_vehicle_amount numeric,
          calculated_total_amount numeric,
          calculation_detail jsonb
        )
        ON CONFLICT (travel_order_id, sequence_no) DO UPDATE
        SET start_at = EXCLUDED.start_at,
            from_place = EXCLUDED.from_place,
            to_place = EXCLUDED.to_place,
            end_at = EXCLUDED.end_at,
            company_or_place = EXCLUDED.company_or_place,
            purpose = EXCLUDED.purpose,
            segment_type = EXCLUDED.segment_type,
            foreign_country_code = EXCLUDED.foreign_country_code,
            foreign_country_name = EXCLUDED.foreign_country_name,
            foreign_meal_currency = EXCLUDED.foreign_meal_currency,
            foreign_meal_rate = EXCLUDED.foreign_meal_rate,
            foreign_exchange_rate = EXCLUDED.foreign_exchange_rate,
            foreign_exchange_rate_date = EXCLUDED.foreign_exchange_rate_date,
            foreign_meal_amount_czk = EXCLUDED.foreign_meal_amount_czk,
            transport_kind = EXCLUDED.transport_kind,
            km = EXCLUDED.km,
            fare_amount = EXCLUDED.fare_amount,
            lodging_amount = EXCLUDED.lodging_amount,
            other_amount = EXCLUDED.other_amount,
            free_meals = EXCLUDED.free_meals,
            calculated_hours = EXCLUDED.calculated_hours,
            calculated_meal_amount = EXCLUDED.calculated_meal_amount,
            calculated_private_vehicle_amount = EXCLUDED.calculated_private_vehicle_amount,
            calculated_total_amount = EXCLUDED.calculated_total_amount,
            calculation_detail = EXCLUDED.calculation_detail,
            updated_at = now()
      ),
      trimmed_lines AS (
        DELETE FROM travel.travel_route_line
        WHERE travel_order_id = (SELECT id FROM saved_order)
          AND sequence_no > jsonb_array_length(:'lines'::jsonb)
        RETURNING id
      ),
      saved_total AS (
        INSERT INTO travel.travel_order_total(
          travel_order_id,
          total_km,
          total_hours,
          transport_amount,
          meal_amount,
          lodging_amount,
          other_amount,
          gross_amount,
          advance_amount,
          balance_amount,
          balance_rounded,
          calculation_snapshot
        )
        VALUES (
          (SELECT id FROM saved_order),
          :'total_km'::numeric,
          :'total_hours'::numeric,
          :'transport_amount'::numeric,
          :'meal_amount'::numeric,
          :'lodging_amount'::numeric,
          :'other_amount'::numeric,
          :'gross_amount'::numeric,
          :'advance_amount'::numeric,
          :'balance_amount'::numeric,
          :'balance_rounded'::numeric,
          :'calculation_snapshot'::jsonb
        )
        ON CONFLICT (travel_order_id) DO UPDATE
        SET total_km = EXCLUDED.total_km,
            total_hours = EXCLUDED.total_hours,
            transport_amount = EXCLUDED.transport_amount,
            meal_amount = EXCLUDED.meal_amount,
            lodging_amount = EXCLUDED.lodging_amount,
            other_amount = EXCLUDED.other_amount,
            gross_amount = EXCLUDED.gross_amount,
            advance_amount = EXCLUDED.advance_amount,
            balance_amount = EXCLUDED.balance_amount,
            balance_rounded = EXCLUDED.balance_rounded,
            calculation_snapshot = EXCLUDED.calculation_snapshot,
            calculated_at = now()
      ),
      saved_accounting_approvals AS (
        INSERT INTO travel.approval_request(
          travel_order_id, step_no, approver_user_id, status, requested_at, due_at, stage
        )
        SELECT
          (SELECT id FROM saved_order),
          1,
          u.id,
          'pending',
          now(),
          now() + interval '2 days',
          'accounting'
        FROM travel.app_user u
        JOIN travel.user_role ur ON ur.user_id = u.id
        JOIN travel.role r ON r.id = ur.role_id AND r.code = 'accountant'
        WHERE u.is_active
          AND u.id <> :'owner_user_id'::uuid
        ON CONFLICT (travel_order_id, step_no, approver_user_id) DO UPDATE
        SET status = 'pending',
            requested_at = now(),
            due_at = now() + interval '2 days',
            decided_at = NULL,
            decision_comment = NULL,
            stage = 'accounting'
        RETURNING id, approver_user_id
      ),
      cancelled_other_approvals AS (
        UPDATE travel.approval_request ar
        SET status = 'cancelled',
            decided_at = now(),
            decision_comment = 'Nahrazeno novym vyberem schvalovatele.'
        WHERE ar.travel_order_id = (SELECT id FROM saved_order)
          AND ar.id NOT IN (SELECT id FROM saved_accounting_approvals)
          AND ar.status = 'pending'
        RETURNING ar.id
      ),
      closed_existing_approval_notifications AS (
        UPDATE travel.notification n
        SET status = 'read',
            read_at = COALESCE(n.read_at, now())
        WHERE n.type_code = 'approval_requested'
          AND n.object_type = 'travel_order'
          AND n.object_id = (SELECT id FROM saved_order)
          AND n.status IN ('queued', 'sent')
          AND n.read_at IS NULL
        RETURNING n.id
      ),
      saved_notifications AS (
        INSERT INTO travel.notification(
          recipient_user_id,
          channel,
          status,
          type_code,
          title,
          message,
          object_type,
          object_id,
          action_url
        )
        SELECT
          sa.approver_user_id,
          'in_app',
          'queued',
          'approval_requested',
          'Nový cestovní příkaz ke kontrole účetní',
          'Cestovní příkaz ' || (SELECT order_no FROM saved_order) || ' čeká na kontrolu účetní.',
          'travel_order',
          (SELECT id FROM saved_order),
          '/approvals'
        FROM saved_accounting_approvals sa
        RETURNING id
      ),
      linked_approvals AS (
        UPDATE travel.approval_request
        SET notification_id = (SELECT id FROM saved_notifications LIMIT 1)
        WHERE id IN (SELECT id FROM saved_accounting_approvals)
        RETURNING id
      )
      SELECT to_jsonb(t)::text
      FROM (
        SELECT
          (SELECT id::text FROM saved_order) AS travel_order_id,
          (SELECT order_no FROM saved_order) AS order_no,
          (SELECT id::text FROM saved_accounting_approvals LIMIT 1) AS approval_request_id,
          (SELECT id::text FROM linked_approvals LIMIT 1) AS linked_approval_request_id,
          (SELECT approver_user_id::text FROM saved_accounting_approvals LIMIT 1) AS approver_user_id,
          (SELECT id::text FROM saved_notifications LIMIT 1) AS notification_id,
          (SELECT count(*) FROM cancelled_other_approvals) AS cancelled_other_approval_count,
          (SELECT count(*) FROM closed_existing_approval_notifications) AS closed_existing_notification_count
      ) t;
    """
    lines_payload = []
    for index, line in enumerate(lines):
        line_calc = calc_lines[index] if index < len(calc_lines) and isinstance(calc_lines[index], dict) else {}
        segment_type = str(line.get("segmentType") or line.get("segment_type") or "domestic")
        if segment_type not in SEGMENT_TYPES:
            segment_type = "domestic"
        lines_payload.append(
            {
                "start_at": line.get("startAt") or "",
                "from_place": line.get("from") or "",
                "to_place": line.get("to") or "",
                "end_at": line.get("endAt") or "",
                "company_or_place": line.get("company") or "",
                "purpose": line.get("purpose") or "",
                "segment_type": segment_type,
                "foreign_country_code": line.get("countryCode") or "",
                "foreign_country_name": line.get("countryName") or "",
                "foreign_meal_currency": normalize_currency_code(line.get("foreignCurrencyCode")) if segment_type == "foreign" else "",
                "foreign_meal_rate": number_like(line.get("foreignMealRate")),
                "foreign_exchange_rate": positive_number_like(line.get("foreignExchangeRate"), 1),
                "foreign_exchange_rate_date": normalize_date_string(line.get("foreignExchangeRateDate")) or "",
                "foreign_meal_amount_czk": number_like(line.get("foreignMealAmountCzk")),
                "transport_kind": line.get("transport") or "private_car",
                "km": number_like(line.get("km")),
                "fare_amount": number_like(line.get("fare")),
                "lodging_amount": number_like(line.get("lodging")),
                "other_amount": number_like(line.get("other")),
                "free_meals": int(float(number_like(line.get("freeMeals")))),
                "calculated_hours": number_like(line_calc.get("hours")),
                "calculated_meal_amount": number_like(line_calc.get("meal")),
                "calculated_private_vehicle_amount": number_like(line_calc.get("privateComp")),
                "calculated_total_amount": number_like(line_calc.get("total")),
                "calculation_detail": {
                    "mealBase": number_like(line_calc.get("mealBase")),
                    "mealReduction": number_like(line_calc.get("mealReduction")),
                    "mealCurrency": line_calc.get("mealCurrency") or ("CZK" if segment_type != "foreign" else normalize_currency_code(line.get("foreignCurrencyCode"))),
                    "mealExchangeRate": number_like(line_calc.get("mealExchangeRate") or line.get("foreignExchangeRate") or 1),
                    "mealForeignAmount": number_like(line_calc.get("mealForeignAmount") or 0),
                    "basicKmRate": number_like((order.get("vehicle") or {}).get("basicKmRate")),
                    "privateKmRate": number_like((order.get("vehicle") or {}).get("privateKmRate")),
                },
            }
        )
    snapshot = build_calculation_snapshot(order_for_save, calc)
    result = run_psql_json(
        sql,
        {
            "owner_user_id": request.current_user["user_id"],
            "travel_request_id": travel_request_id,
            "selected_approver_user_id": selected_approver_user_id,
            "order_no": order_no,
            "purpose": trip.get("purpose") or "",
            "destination": trip.get("destination") or "",
            "visited_companies": trip.get("visitedCompanies") or "",
            "companions": trip.get("companions") or "",
            "planned_start_at": trip.get("startAt") or "",
            "planned_end_at": trip.get("endAt") or "",
            "report_date": trip.get("reportDate") or "",
            "expected_expense": number_like(trip.get("expectedExpense")),
            "advance_amount": number_like(trip.get("advance")),
            "currency_code": normalize_currency_code(trip.get("currencyCode")),
            "lines": json.dumps(lines_payload),
            "total_km": number_like(calc.get("totalKm")),
            "total_hours": number_like(calc.get("totalHours")),
            "transport_amount": number_like(calc.get("totalTransport")),
            "meal_amount": number_like(calc.get("totalMeals")),
            "lodging_amount": number_like(calc.get("totalLodging")),
            "other_amount": number_like(calc.get("totalOther")),
            "gross_amount": number_like(calc.get("totalGross")),
            "balance_amount": number_like(calc.get("balance")),
            "balance_rounded": number_like(calc.get("balanceRounded")),
            "calculation_snapshot": json.dumps(snapshot),
        },
    )
    if result and result.get("travel_order_id"):
        result["attachment_sync"] = save_order_attachments(
            result["travel_order_id"],
            order_for_save.get("attachments") or [],
            request.current_user["user_id"],
        )
        used_vehicle_id = used_saved_vehicle_id(order_for_save)
        if used_vehicle_id:
            result["vehicle_erp_sync"] = mark_vehicle_for_erp_after_order_use(
                request.current_user["user_id"],
                used_vehicle_id,
                result["travel_order_id"],
            )
    return jsonify({"submission": result})


@app.post("/api/travel-orders/save-draft")
@require_auth
def save_travel_order_draft():
    payload = request.get_json(silent=True) or {}
    order = payload.get("order") or {}
    calc = payload.get("calculation") or {}
    user_id = request.current_user["user_id"]

    existing_order_id = valid_uuid(order.get("serverId") or order.get("travelOrderId") or "")
    order_no = ensure_unique_order_number(str(order.get("number") or "").strip(), existing_order_id)
    trip = order.get("trip") or {}
    snapshot = build_calculation_snapshot(order, calc)

    sql = """
      WITH saved_order AS (
        INSERT INTO travel.travel_order(
          id,
          order_no,
          owner_user_id,
          employee_profile_id,
          status,
          purpose,
          destination,
          visited_companies,
          companions,
          planned_start_at,
          planned_end_at,
          report_date,
          expected_expense,
          advance_amount,
          currency_code,
          export_status
        )
        VALUES (
          COALESCE(NULLIF(:'existing_order_id', '')::uuid, gen_random_uuid()),
          :'order_no',
          :'owner_user_id'::uuid,
          (SELECT id FROM travel.employee_profile WHERE user_id = :'owner_user_id'::uuid LIMIT 1),
          'draft',
          NULLIF(:'purpose', ''),
          NULLIF(:'destination', ''),
          NULLIF(:'visited_companies', ''),
          NULLIF(:'companions', ''),
          NULLIF(:'planned_start_at', '')::timestamptz,
          NULLIF(:'planned_end_at', '')::timestamptz,
          NULLIF(:'report_date', '')::date,
          :'expected_expense'::numeric,
          :'advance_amount'::numeric,
          :'currency_code',
          'not_ready'
        )
        ON CONFLICT (order_no) DO UPDATE
        SET owner_user_id = EXCLUDED.owner_user_id,
            employee_profile_id = EXCLUDED.employee_profile_id,
            status = 'draft',
            purpose = EXCLUDED.purpose,
            destination = EXCLUDED.destination,
            visited_companies = EXCLUDED.visited_companies,
            companions = EXCLUDED.companions,
            planned_start_at = EXCLUDED.planned_start_at,
            planned_end_at = EXCLUDED.planned_end_at,
            report_date = EXCLUDED.report_date,
            expected_expense = EXCLUDED.expected_expense,
            advance_amount = EXCLUDED.advance_amount,
            currency_code = EXCLUDED.currency_code,
            export_status = 'not_ready'::travel.export_status,
            submitted_at = NULL,
            approved_at = NULL,
            rejected_at = NULL,
            current_approver_user_id = NULL,
            helios_document_id = NULL,
            helios_export_payload = NULL,
            helios_exported_at = NULL,
            updated_at = now()
        WHERE travel.travel_order.owner_user_id = :'owner_user_id'::uuid
        RETURNING id, order_no
      ),
      saved_total AS (
        INSERT INTO travel.travel_order_total(
          travel_order_id,
          total_km,
          total_hours,
          transport_amount,
          meal_amount,
          lodging_amount,
          other_amount,
          gross_amount,
          advance_amount,
          balance_amount,
          balance_rounded,
          calculation_snapshot
        )
        VALUES (
          (SELECT id FROM saved_order),
          :'total_km'::numeric,
          :'total_hours'::numeric,
          :'transport_amount'::numeric,
          :'meal_amount'::numeric,
          :'lodging_amount'::numeric,
          :'other_amount'::numeric,
          :'gross_amount'::numeric,
          :'advance_amount'::numeric,
          :'balance_amount'::numeric,
          :'balance_rounded'::numeric,
          :'calculation_snapshot'::jsonb
        )
        ON CONFLICT (travel_order_id) DO UPDATE
        SET total_km = EXCLUDED.total_km,
            total_hours = EXCLUDED.total_hours,
            transport_amount = EXCLUDED.transport_amount,
            meal_amount = EXCLUDED.meal_amount,
            lodging_amount = EXCLUDED.lodging_amount,
            other_amount = EXCLUDED.other_amount,
            gross_amount = EXCLUDED.gross_amount,
            advance_amount = EXCLUDED.advance_amount,
            balance_amount = EXCLUDED.balance_amount,
            balance_rounded = EXCLUDED.balance_rounded,
            calculation_snapshot = EXCLUDED.calculation_snapshot,
            calculated_at = now()
      )
      SELECT to_jsonb(t)::text
      FROM (
        SELECT id::text AS travel_order_id, order_no
        FROM saved_order
      ) t;
    """
    saved = run_psql_json(
        sql,
        {
            "existing_order_id": existing_order_id or "",
            "order_no": order_no,
            "owner_user_id": user_id,
            "purpose": trip.get("purpose") or "",
            "destination": trip.get("destination") or "",
            "visited_companies": trip.get("visitedCompanies") or "",
            "companions": trip.get("companions") or "",
            "planned_start_at": trip.get("startAt") or "",
            "planned_end_at": trip.get("endAt") or "",
            "report_date": trip.get("reportDate") or "",
            "expected_expense": number_like(trip.get("expectedExpense")),
            "advance_amount": number_like(trip.get("advance")),
            "currency_code": normalize_currency_code(trip.get("currencyCode")),
            "total_km": number_like(calc.get("totalKm")),
            "total_hours": number_like(calc.get("totalHours")),
            "transport_amount": number_like(calc.get("totalTransport")),
            "meal_amount": number_like(calc.get("totalMeals")),
            "lodging_amount": number_like(calc.get("totalLodging")),
            "other_amount": number_like(calc.get("totalOther")),
            "gross_amount": number_like(calc.get("totalGross")),
            "balance_amount": number_like(calc.get("balance")),
            "balance_rounded": number_like(calc.get("balanceRounded")),
            "calculation_snapshot": json.dumps(snapshot),
        },
    )
    if not saved:
        return jsonify({"error": "save_draft_failed"}), 400
    return jsonify({"saved": saved})


@app.post("/api/travel-orders/<travel_order_id>/return-to-draft")
@require_auth
def return_travel_order_to_draft(travel_order_id):
    order_id = valid_uuid(travel_order_id)
    if not order_id:
        return jsonify({"error": "invalid_travel_order"}), 400

    sql = """
      WITH target AS (
        SELECT
          id,
          order_no,
          owner_user_id,
          status::text AS status,
          export_status::text AS export_status,
          helios_document_id
        FROM travel.travel_order
        WHERE id = :'travel_order_id'::uuid
          AND owner_user_id = :'user_id'::uuid
        FOR UPDATE
      ),
      updated AS (
        UPDATE travel.travel_order o
        SET status = 'draft'::travel.order_status,
            export_status = 'not_ready'::travel.export_status,
            submitted_at = NULL,
            approved_at = NULL,
            rejected_at = NULL,
            current_approver_user_id = NULL,
            helios_document_id = NULL,
            helios_export_payload = NULL,
            helios_exported_at = NULL,
            updated_at = now()
        WHERE o.id = (SELECT id FROM target)
          AND (SELECT status FROM target) IN ('approved', 'submitted', 'rejected')
          AND COALESCE((SELECT export_status FROM target), '') <> 'exported'
          AND (SELECT helios_document_id FROM target) IS NULL
        RETURNING o.id, o.order_no, o.status::text AS status, o.export_status::text AS export_status, o.updated_at
      ),
      closed_approvals AS (
        UPDATE travel.approval_request ar
        SET status = CASE
              WHEN ar.status = 'pending' THEN 'cancelled'::travel.approval_status
              ELSE ar.status
            END,
            decided_at = COALESCE(ar.decided_at, now()),
            decision_comment = COALESCE(ar.decision_comment, 'VrĂˇceno vlastnĂ­kem do Ăşprav.')
        WHERE ar.travel_order_id = (SELECT id FROM updated)
          AND ar.status = 'pending'
        RETURNING ar.id
      ),
      closed_notifications AS (
        UPDATE travel.notification n
        SET status = 'read'::travel.notification_status,
            read_at = COALESCE(n.read_at, now())
        WHERE n.object_type = 'travel_order'
          AND n.object_id = (SELECT id FROM updated)
          AND n.type_code = 'approval_requested'
          AND n.status IN ('queued', 'sent')
          AND n.read_at IS NULL
        RETURNING n.id
      )
      SELECT jsonb_build_object(
        'found', EXISTS (SELECT 1 FROM target),
        'updated', EXISTS (SELECT 1 FROM updated),
        'invalidStatus', EXISTS (
          SELECT 1 FROM target
          WHERE status NOT IN ('approved', 'submitted', 'rejected')
        ),
        'imported', EXISTS (
          SELECT 1 FROM target
          WHERE export_status = 'exported'
             OR helios_document_id IS NOT NULL
        ),
        'travelOrderId', COALESCE((SELECT id::text FROM updated), (SELECT id::text FROM target)),
        'orderNo', COALESCE((SELECT order_no FROM updated), (SELECT order_no FROM target)),
        'status', COALESCE((SELECT status FROM updated), (SELECT status FROM target)),
        'exportStatus', COALESCE((SELECT export_status FROM updated), (SELECT export_status FROM target)),
        'heliosDocumentId', COALESCE((SELECT helios_document_id FROM target), ''),
        'updatedAt', (SELECT updated_at FROM updated),
        'closedApprovalCount', (SELECT count(*) FROM closed_approvals),
        'closedNotificationCount', (SELECT count(*) FROM closed_notifications)
      )::text;
    """
    result = run_psql_json(
        sql,
        {
            "travel_order_id": order_id,
            "user_id": request.current_user["user_id"],
        },
    )
    if not result.get("found"):
        return jsonify({"error": "travel_order_not_found"}), 404
    if not result.get("updated"):
        if result.get("imported"):
            error = "travel_order_imported"
        elif result.get("invalidStatus"):
            error = "travel_order_not_returnable"
        else:
            error = "travel_order_not_updated"
        return jsonify({"error": error, **result}), 409
    try:
        result["helios_staging_sync"] = sync_helios_import_staging(
            f"return-to-draft:{result.get('travelOrderId') or order_id}"
        )
    except Exception as exc:
        result["helios_staging_sync"] = {
            "ok": False,
            "error": str(exc),
        }
    return jsonify({"order": result})


def used_saved_vehicle_id(order: dict) -> str:
    vehicle = order.get("vehicle") if isinstance(order.get("vehicle"), dict) else {}
    vehicle_id = valid_uuid(vehicle.get("id"))
    if not vehicle_id:
        return ""

    route_lines = order.get("routeLines") if isinstance(order.get("routeLines"), list) else []
    for line in route_lines:
        if not isinstance(line, dict):
            continue
        transport = str(line.get("transport") or "private_car")
        if transport in {"private_car", "company_car"}:
            return vehicle_id
    return ""


def mark_vehicle_for_erp_after_order_use(user_id: str, vehicle_id: str, travel_order_id: str) -> dict:
    sql = """
      WITH selected AS (
        SELECT
          id,
          helios_id,
          source_system,
          helios_export_status
        FROM travel.vehicle
        WHERE id = :'vehicle_id'::uuid
          AND owner_user_id = :'user_id'::uuid
          AND is_active
        LIMIT 1
      ),
      queued AS (
        UPDATE travel.vehicle vehicle
        SET helios_export_status = 'queued'::travel.export_status,
            helios_export_requested_at = now(),
            helios_export_failed_at = NULL,
            helios_export_error = NULL,
            helios_export_travel_order_id = :'travel_order_id'::uuid,
            updated_at = now()
        WHERE vehicle.id = (SELECT id FROM selected)
          AND (SELECT helios_id FROM selected) IS NULL
          AND (SELECT helios_export_status FROM selected) <> 'queued'::travel.export_status
        RETURNING vehicle.id
      )
      SELECT jsonb_build_object(
        'vehicle_id', (SELECT id::text FROM selected),
        'action', CASE
          WHEN NOT EXISTS (SELECT 1 FROM selected) THEN 'not_found'
          WHEN (SELECT helios_id FROM selected) IS NOT NULL THEN 'already_in_erp'
          WHEN EXISTS (SELECT 1 FROM queued) THEN 'queued'
          WHEN (SELECT helios_export_status FROM selected) = 'queued'::travel.export_status THEN 'already_queued'
          ELSE 'unchanged'
        END,
        'helios_id', COALESCE((SELECT helios_id FROM selected), ''),
        'source_system', COALESCE((SELECT source_system::text FROM selected), 'local'),
        'helios_export_status', COALESCE(
          (SELECT 'queued' FROM queued LIMIT 1),
          (SELECT helios_export_status::text FROM selected),
          'not_ready'
        )
      )::text;
    """
    return run_psql_json(
        sql,
        {
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "travel_order_id": travel_order_id,
        },
    ) or {"action": "not_found"}


@app.post("/api/approval-requests/<approval_request_id>/decision")
@require_auth
def approval_decision(approval_request_id):
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip()
    comment = str(payload.get("comment") or "").strip()
    if action not in {"approved", "returned", "rejected"}:
        return jsonify({"error": "invalid_action"}), 400

    selected = run_psql_json(
        """
        SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
        FROM (
          SELECT
            ar.id::text AS id,
            ar.travel_order_id::text AS travel_order_id,
            ar.stage::text AS stage,
            ar.status::text AS status,
            o.order_no,
            o.owner_user_id::text AS owner_user_id,
            o.final_approver_user_id::text AS final_approver_user_id
          FROM travel.approval_request ar
          JOIN travel.travel_order o ON o.id = ar.travel_order_id
          WHERE ar.id = :'approval_request_id'::uuid
            AND ar.status = 'pending'
            AND (
              ar.approver_user_id = :'approver_user_id'::uuid
              OR :'is_admin'::boolean
            )
          LIMIT 1
        ) t;
        """,
        {
            "approval_request_id": approval_request_id,
            "approver_user_id": request.current_user["user_id"],
            "is_admin": "true" if has_role(request.current_user, "admin") else "false",
        },
    ) or {}
    if not selected.get("id"):
        return jsonify({"error": "approval_not_found"}), 404

    stage = str(selected.get("stage") or "manager")
    travel_order_id = str(selected.get("travel_order_id") or "")
    owner_user_id = str(selected.get("owner_user_id") or "")
    order_no = str(selected.get("order_no") or "")

    if stage == "accounting":
        if action not in {"approved", "returned"}:
            return jsonify({"error": "invalid_action_for_accounting"}), 400
        if action == "returned" and not comment:
            return jsonify({"error": "missing_return_comment"}), 400

        if action == "approved":
            manager_user_id = str(selected.get("final_approver_user_id") or "").strip()
            if not valid_uuid(manager_user_id):
                return jsonify({"error": "missing_final_approver"}), 400
            result = run_psql_json(
                """
                WITH decided AS (
                  UPDATE travel.approval_request
                  SET status = 'approved',
                      decided_at = now(),
                      decision_comment = NULLIF(:'comment', '')
                  WHERE id = :'approval_request_id'::uuid
                  RETURNING travel_order_id
                ),
                cancelled_other_accountants AS (
                  UPDATE travel.approval_request ar
                  SET status = 'cancelled',
                      decided_at = COALESCE(ar.decided_at, now()),
                      decision_comment = COALESCE(ar.decision_comment, 'Schváleno jinou účetní.')
                  WHERE ar.travel_order_id = (SELECT travel_order_id FROM decided)
                    AND ar.stage = 'accounting'
                    AND ar.status = 'pending'
                    AND ar.id <> :'approval_request_id'::uuid
                  RETURNING id
                ),
                manager_approval AS (
                  INSERT INTO travel.approval_request(
                    travel_order_id, step_no, approver_user_id, status, requested_at, due_at, stage
                  )
                  VALUES (
                    (SELECT travel_order_id FROM decided),
                    2,
                    :'manager_user_id'::uuid,
                    'pending',
                    now(),
                    now() + interval '2 days',
                    'manager'
                  )
                  ON CONFLICT (travel_order_id, step_no, approver_user_id) DO UPDATE
                  SET status = 'pending',
                      requested_at = now(),
                      due_at = now() + interval '2 days',
                      decided_at = NULL,
                      decision_comment = NULL,
                      stage = 'manager'
                  RETURNING id
                ),
                order_update AS (
                  UPDATE travel.travel_order
                  SET status = 'submitted',
                      current_approver_user_id = :'manager_user_id'::uuid,
                      updated_at = now()
                  WHERE id = (SELECT travel_order_id FROM decided)
                  RETURNING id, order_no
                )
                SELECT to_jsonb(t)::text
                FROM (
                  SELECT
                    (SELECT id::text FROM order_update) AS travel_order_id,
                    (SELECT order_no FROM order_update) AS order_no,
                    (SELECT id::text FROM manager_approval) AS next_approval_request_id,
                    (SELECT count(*) FROM cancelled_other_accountants) AS cancelled_other_accountants
                ) t;
                """,
                {
                    "approval_request_id": approval_request_id,
                    "comment": comment,
                    "manager_user_id": manager_user_id,
                },
            ) or {}
            if not result.get("travel_order_id"):
                return jsonify({"error": "approval_transition_failed"}), 400

            manager_contact = get_user_contact(str(selected.get("final_approver_user_id") or ""))
            to_email = str(manager_contact.get("email") or "").strip()
            email_sent = False
            if to_email:
                email_sent, _ = send_app_email(
                    to_email,
                    f"Cestovní příkaz ke schválení: {order_no}",
                    f"Dobrý den,\n\ncestovní příkaz {order_no} prošel kontrolou účetní a čeká na vaše schválení.\n",
                )
            result["emailNextApproverSent"] = email_sent
            return jsonify({"decision": result})

        result = run_psql_json(
            """
            WITH decided AS (
              UPDATE travel.approval_request
              SET status = 'returned',
                  decided_at = now(),
                  decision_comment = NULLIF(:'comment', ''),
                  rejection_reason = NULLIF(:'comment', '')
              WHERE id = :'approval_request_id'::uuid
              RETURNING travel_order_id
            ),
            cancelled_pending AS (
              UPDATE travel.approval_request ar
              SET status = 'cancelled',
                  decided_at = COALESCE(ar.decided_at, now()),
                  decision_comment = COALESCE(ar.decision_comment, 'Vráceno účetní k doplnění.')
              WHERE ar.travel_order_id = (SELECT travel_order_id FROM decided)
                AND ar.status = 'pending'
                AND ar.id <> :'approval_request_id'::uuid
              RETURNING id
            ),
            order_update AS (
              UPDATE travel.travel_order
              SET status = 'draft',
                  current_approver_user_id = NULL,
                  export_status = 'not_ready',
                  updated_at = now()
              WHERE id = (SELECT travel_order_id FROM decided)
              RETURNING id, order_no, owner_user_id
            )
            SELECT to_jsonb(t)::text
            FROM (
              SELECT
                (SELECT id::text FROM order_update) AS travel_order_id,
                (SELECT order_no FROM order_update) AS order_no,
                (SELECT owner_user_id::text FROM order_update) AS owner_user_id,
                (SELECT count(*) FROM cancelled_pending) AS cancelled_pending_count
            ) t;
            """,
            {"approval_request_id": approval_request_id, "comment": comment},
        ) or {}
        if not result.get("travel_order_id"):
            return jsonify({"error": "approval_transition_failed"}), 400

        owner = get_user_contact(owner_user_id)
        to_email = str(owner.get("email") or "").strip()
        email_sent = False
        if to_email:
            email_sent, _ = send_app_email(
                to_email,
                f"Cestovní příkaz vrácen účetní: {order_no}",
                f"Dobrý den,\n\ncestovní příkaz {order_no} byl vrácen účetní k doplnění.\nDůvod: {comment}\n",
            )
        result["emailOwnerSent"] = email_sent
        return jsonify({"decision": result})

    # manager stage
    if action not in {"approved", "rejected"}:
        return jsonify({"error": "invalid_action_for_manager"}), 400
    if action == "rejected" and not comment:
        return jsonify({"error": "missing_rejection_reason"}), 400

    status_map = {"approved": "approved", "rejected": "rejected"}
    result = run_psql_json(
        """
        WITH decided AS (
          UPDATE travel.approval_request ar
          SET status = :'action'::travel.approval_status,
              decided_at = now(),
              decision_comment = NULLIF(:'comment', ''),
              rejection_reason = CASE WHEN :'action' = 'rejected' THEN NULLIF(:'comment', '') ELSE NULL END
          WHERE ar.id = :'approval_request_id'::uuid
          RETURNING ar.travel_order_id
        ),
        changed_order AS (
          UPDATE travel.travel_order o
          SET status = :'order_status'::travel.order_status,
              current_approver_user_id = NULL,
              approved_at = CASE WHEN :'action' = 'approved' THEN now() ELSE approved_at END,
              rejected_at = CASE WHEN :'action' = 'rejected' THEN now() ELSE rejected_at END,
              export_status = CASE
                WHEN :'action' = 'approved' THEN 'ready'::travel.export_status
                ELSE 'not_ready'::travel.export_status
              END
          WHERE o.id = (SELECT travel_order_id FROM decided)
          RETURNING o.id, o.order_no, o.owner_user_id
        )
        SELECT to_jsonb(t)::text
        FROM (
          SELECT
            (SELECT id::text FROM changed_order) AS travel_order_id,
            (SELECT order_no FROM changed_order) AS order_no,
            (SELECT owner_user_id::text FROM changed_order) AS owner_user_id
        ) t;
        """,
        {
            "approval_request_id": approval_request_id,
            "action": action,
            "comment": comment,
            "order_status": status_map[action],
        },
    ) or {}
    if not result.get("travel_order_id"):
        return jsonify({"error": "approval_transition_failed"}), 400

    owner = get_user_contact(owner_user_id)
    to_email = str(owner.get("email") or "").strip()
    email_sent = False
    if to_email:
        text = "schválen" if action == "approved" else f"zamítnut. Důvod: {comment}"
        email_sent, _ = send_app_email(
            to_email,
            f"Rozhodnutí o cestovním příkazu: {order_no}",
            f"Dobrý den,\n\nváš cestovní příkaz {order_no} byl {text}\n",
        )
    result["emailOwnerSent"] = email_sent
    if action == "approved":
        try:
            result["helios_staging_sync"] = sync_helios_import_staging(
                f"approval:{result.get('travel_order_id') or ''}"
            )
        except Exception as exc:
            result["helios_staging_sync"] = {"ok": False, "error": str(exc)}
    return jsonify({"decision": result})


def save_user_default_approver(user_id: str, approver_user_id: str) -> dict:
    validate_sql = """
      WITH profile AS (
        SELECT id, user_id
        FROM travel.employee_profile
        WHERE user_id = :'user_id'::uuid
        LIMIT 1
      ),
      option_count AS (
        SELECT count(*) AS count
        FROM travel.employee_approver_option option
        WHERE option.employee_profile_id = (SELECT id FROM profile)
          AND option.is_active
          AND option.approver_user_id <> (SELECT user_id FROM profile)
      ),
      selected AS (
        SELECT approver.id
        FROM travel.app_user approver
        JOIN travel.user_role ur ON ur.user_id = approver.id
        JOIN travel.role role ON role.id = ur.role_id AND role.code = 'approver'
        LEFT JOIN travel.employee_approver_option option
          ON option.employee_profile_id = (SELECT id FROM profile)
         AND option.approver_user_id = approver.id
         AND option.is_active
        WHERE approver.id = :'approver_user_id'::uuid
          AND approver.is_active
          AND approver.id <> (SELECT user_id FROM profile)
          AND (
            (SELECT count FROM option_count) = 0
            OR option.id IS NOT NULL
          )
        LIMIT 1
      ),
      updated AS (
        UPDATE travel.employee_profile
        SET default_approver_user_id = (SELECT id FROM selected)
        WHERE id = (SELECT id FROM profile)
          AND EXISTS (SELECT 1 FROM selected)
        RETURNING id
      )
      SELECT jsonb_build_object(
        'updated', EXISTS (SELECT 1 FROM updated),
        'profile_id', (SELECT id::text FROM profile),
        'has_limited_options', (SELECT count FROM option_count) > 0,
        'approver_user_id', (SELECT id::text FROM selected)
      )::text;
    """
    result = run_psql_json(validate_sql, {"user_id": user_id, "approver_user_id": approver_user_id})
    if not result or not result.get("updated"):
        raise DatabaseError("Selected approver is not available for this employee.")

    if result.get("has_limited_options"):
        clear_sql = """
          WITH cleared AS (
            UPDATE travel.employee_approver_option
            SET is_default = false,
                updated_at = now()
            WHERE employee_profile_id = :'profile_id'::uuid
              AND is_default
            RETURNING id
          )
          SELECT jsonb_build_object('cleared_default_count', (SELECT count(*) FROM cleared))::text;
        """
        clear_result = run_psql_json(clear_sql, {"profile_id": result["profile_id"]})
        mark_sql = """
          WITH marked AS (
            UPDATE travel.employee_approver_option
            SET is_default = true,
                is_active = true,
                updated_at = now()
            WHERE employee_profile_id = :'profile_id'::uuid
              AND approver_user_id = :'approver_user_id'::uuid
            RETURNING id
          )
          SELECT jsonb_build_object('marked_default_count', (SELECT count(*) FROM marked))::text;
        """
        mark_result = run_psql_json(
            mark_sql,
            {"profile_id": result["profile_id"], "approver_user_id": approver_user_id},
        )
        result = {**result, **(clear_result or {}), **(mark_result or {})}

    return result


def save_employee_approver_options(employee_profile_id: str, approver_options: list[dict], legacy_default_id: str = "") -> dict:
    if not approver_options and legacy_default_id:
        approver_options = [{"id": valid_uuid(legacy_default_id), "is_default": True}]

    approver_ids = [option["id"] for option in approver_options if option.get("id")]
    deactivate_sql = """
      WITH requested AS (
        SELECT value::uuid AS id
        FROM jsonb_array_elements_text(:'approver_ids'::jsonb)
      ),
      deactivated AS (
        UPDATE travel.employee_approver_option option
        SET is_active = false,
            is_default = false,
            updated_at = now()
        WHERE option.employee_profile_id = :'employee_profile_id'::uuid
          AND option.is_active
          AND NOT EXISTS (SELECT 1 FROM requested WHERE requested.id = option.approver_user_id)
        RETURNING id
      ),
      cleared AS (
        UPDATE travel.employee_approver_option option
        SET is_default = false,
            updated_at = now()
        WHERE option.employee_profile_id = :'employee_profile_id'::uuid
          AND option.is_default
        RETURNING id
      )
      SELECT jsonb_build_object(
        'deactivated_count', (SELECT count(*) FROM deactivated),
        'cleared_default_count', (SELECT count(*) FROM cleared)
      )::text;
    """
    deactivated = run_psql_json(
        deactivate_sql,
        {"employee_profile_id": employee_profile_id, "approver_ids": json.dumps(approver_ids)},
    )

    upsert_sql = """
      WITH requested AS (
        SELECT
          NULLIF(option.id, '')::uuid AS approver_user_id,
          COALESCE(option.is_default, false) AS is_default
        FROM jsonb_to_recordset(:'approvers'::jsonb) AS option(id text, is_default boolean)
      ),
      profile AS (
        SELECT id, user_id
        FROM travel.employee_profile
        WHERE id = :'employee_profile_id'::uuid
        LIMIT 1
      ),
      valid_requested AS (
        SELECT requested.approver_user_id, requested.is_default
        FROM requested
        JOIN profile ON profile.id = :'employee_profile_id'::uuid
        JOIN travel.app_user approver ON approver.id = requested.approver_user_id AND approver.is_active
        JOIN travel.user_role ur ON ur.user_id = approver.id
        JOIN travel.role role ON role.id = ur.role_id AND role.code = 'approver'
        WHERE approver.id <> profile.user_id
      ),
      saved AS (
        INSERT INTO travel.employee_approver_option(employee_profile_id, approver_user_id, is_default, source_system, is_active)
        SELECT :'employee_profile_id'::uuid, approver_user_id, is_default, 'local', true
        FROM valid_requested
        ON CONFLICT (employee_profile_id, approver_user_id) DO UPDATE
        SET is_default = EXCLUDED.is_default,
            is_active = true,
            source_system = CASE
              WHEN travel.employee_approver_option.source_system = 'helios' THEN 'mixed'::travel.user_source
              ELSE travel.employee_approver_option.source_system
            END,
            updated_at = now()
        RETURNING approver_user_id, is_default
      ),
      default_choice AS (
        SELECT approver_user_id
        FROM saved
        WHERE is_default
        LIMIT 1
      ),
      updated_profile AS (
        UPDATE travel.employee_profile
        SET default_approver_user_id = (SELECT approver_user_id FROM default_choice)
        WHERE id = :'employee_profile_id'::uuid
        RETURNING id
      )
      SELECT jsonb_build_object(
        'saved_count', (SELECT count(*) FROM saved),
        'default_approver_user_id', (SELECT approver_user_id::text FROM default_choice)
      )::text;
    """
    upserted = run_psql_json(
        upsert_sql,
        {"employee_profile_id": employee_profile_id, "approvers": json.dumps(approver_options)},
    )

    if not approver_options:
        clear_profile_sql = """
          WITH updated AS (
            UPDATE travel.employee_profile
            SET default_approver_user_id = NULL
            WHERE id = :'employee_profile_id'::uuid
            RETURNING id
          )
          SELECT jsonb_build_object('profile_cleared', (SELECT count(*) FROM updated))::text;
        """
        cleared = run_psql_json(clear_profile_sql, {"employee_profile_id": employee_profile_id})
    else:
        cleared = {}

    return {**(deactivated or {}), **(upserted or {}), **(cleared or {})}


def save_user_vehicles(user_id: str, vehicles: list[dict]) -> dict:
    requested_ids = [vehicle["id"] for vehicle in vehicles if vehicle.get("id")]
    deactivate_sql = """
      WITH requested AS (
        SELECT value::uuid AS id
        FROM jsonb_array_elements_text(:'vehicle_ids'::jsonb)
      ),
      deactivated AS (
        UPDATE travel.vehicle vehicle
        SET is_active = false,
            is_default = false,
            updated_at = now()
        WHERE vehicle.owner_user_id = :'user_id'::uuid
          AND vehicle.is_active
          AND NOT EXISTS (
            SELECT 1 FROM requested WHERE requested.id = vehicle.id
          )
        RETURNING id
      )
      SELECT jsonb_build_object('deactivated_count', (SELECT count(*) FROM deactivated))::text;
    """
    deactivate_result = run_psql_json(
        deactivate_sql,
        {"user_id": user_id, "vehicle_ids": json.dumps(requested_ids)},
    )

    clear_defaults_sql = """
      WITH cleared AS (
        UPDATE travel.vehicle
        SET is_default = false,
            updated_at = now()
        WHERE owner_user_id = :'user_id'::uuid
          AND is_default
        RETURNING id
      )
      SELECT jsonb_build_object('cleared_default_count', (SELECT count(*) FROM cleared))::text;
    """
    clear_result = run_psql_json(clear_defaults_sql, {"user_id": user_id})

    upsert_sql = """
      WITH requested AS (
        SELECT
          NULLIF(vehicle.client_id, '') AS client_id,
          NULLIF(vehicle.id, '')::uuid AS requested_id,
          NULLIF(vehicle.brand, '') AS brand,
          NULLIF(vehicle.plate, '') AS plate,
          NULLIF(vehicle.engine_volume, '')::integer AS engine_volume_cc,
          COALESCE(NULLIF(vehicle.fuel_type, '')::travel.fuel_type, 'ba95') AS fuel_type,
          COALESCE(NULLIF(vehicle.consumption, '')::numeric, 0) AS consumption_l_per_100km,
          NULLIF(vehicle.secondary_fuel_type, '')::travel.fuel_type AS secondary_fuel_type,
          COALESCE(NULLIF(vehicle.secondary_consumption, '')::numeric, 0) AS secondary_consumption_per_100km,
          COALESCE(vehicle.is_default, false) AS is_default
        FROM jsonb_to_recordset(:'vehicles'::jsonb) AS vehicle(
          client_id text,
          id text,
          brand text,
          plate text,
          engine_volume text,
          fuel_type text,
          consumption text,
          secondary_fuel_type text,
          secondary_consumption text,
          is_default boolean
        )
      ),
      safe_requested AS (
        SELECT
          requested.client_id,
          COALESCE(existing.id, requested.requested_id, gen_random_uuid()) AS vehicle_id,
          requested.brand,
          requested.plate,
          requested.engine_volume_cc,
          requested.fuel_type,
          requested.consumption_l_per_100km,
          requested.secondary_fuel_type,
          requested.secondary_consumption_per_100km,
          requested.is_default
        FROM requested
        LEFT JOIN travel.vehicle existing
          ON existing.id = requested.requested_id
         AND existing.owner_user_id = :'user_id'::uuid
      ),
      saved AS (
        INSERT INTO travel.vehicle(
          id,
          owner_user_id,
          brand,
          plate,
          engine_volume_cc,
          fuel_type,
          consumption_l_per_100km,
          secondary_fuel_type,
          secondary_consumption_per_100km,
          is_private,
          is_default,
          is_active
        )
        SELECT
          vehicle_id,
          :'user_id'::uuid,
          brand,
          plate,
          engine_volume_cc,
          fuel_type,
          consumption_l_per_100km,
          secondary_fuel_type,
          secondary_consumption_per_100km,
          true,
          is_default,
          true
        FROM safe_requested
        ON CONFLICT (id) DO UPDATE
        SET brand = EXCLUDED.brand,
            plate = EXCLUDED.plate,
            engine_volume_cc = EXCLUDED.engine_volume_cc,
            fuel_type = EXCLUDED.fuel_type,
            consumption_l_per_100km = EXCLUDED.consumption_l_per_100km,
            secondary_fuel_type = EXCLUDED.secondary_fuel_type,
            secondary_consumption_per_100km = EXCLUDED.secondary_consumption_per_100km,
            is_private = EXCLUDED.is_private,
            is_default = EXCLUDED.is_default,
            is_active = true,
            updated_at = now()
        RETURNING id, is_default
      )
      ,
      saved_with_client AS (
        SELECT saved.id, saved.is_default, safe_requested.client_id
        FROM saved
        JOIN safe_requested ON safe_requested.vehicle_id = saved.id
      )
      SELECT jsonb_build_object(
        'saved_count', (SELECT count(*) FROM saved),
        'default_vehicle_id', (SELECT id::text FROM saved WHERE is_default ORDER BY id LIMIT 1),
        'vehicles', COALESCE((
          SELECT jsonb_agg(jsonb_build_object('id', id::text, 'client_id', client_id))
          FROM saved_with_client
        ), '[]'::jsonb)
      )::text;
    """
    upsert_result = run_psql_json(upsert_sql, {"user_id": user_id, "vehicles": json.dumps(vehicles)})

    default_vehicle_id = (upsert_result or {}).get("default_vehicle_id") or ""
    profile_sql = """
      WITH updated AS (
        UPDATE travel.employee_profile
        SET default_vehicle_id = NULLIF(:'default_vehicle_id', '')::uuid
        WHERE user_id = :'user_id'::uuid
        RETURNING id
      )
      SELECT jsonb_build_object('profile_updated', (SELECT count(*) FROM updated))::text;
    """
    profile_result = run_psql_json(
        profile_sql,
        {"user_id": user_id, "default_vehicle_id": default_vehicle_id},
    )
    document_result = save_vehicle_documents(
        user_id,
        vehicles,
        (upsert_result or {}).get("vehicles") or [],
    )

    return {
        **(deactivate_result or {}),
        **(clear_result or {}),
        **(upsert_result or {}),
        **(profile_result or {}),
        "document_sync": document_result,
    }


def save_vehicle_documents(user_id: str, vehicles: list[dict], saved_vehicle_rows: list[dict]) -> dict:
    vehicle_id_by_client = {
        str(row.get("client_id") or ""): valid_uuid(row.get("id"))
        for row in saved_vehicle_rows
        if isinstance(row, dict)
    }
    saved_count = 0
    skipped_count = 0
    removed_count = 0
    uploader_id = valid_uuid(user_id)

    for vehicle in vehicles:
        vehicle_id = valid_uuid(vehicle.get("id")) or vehicle_id_by_client.get(str(vehicle.get("client_id") or ""))
        if not vehicle_id:
            skipped_count += len(vehicle.get("documents") or [])
            continue

        documents = vehicle.get("documents") or []
        kept_ids = [document["id"] for document in documents if document.get("id")]
        delete_sql = """
          WITH kept AS (
            SELECT value::uuid AS id
            FROM jsonb_array_elements_text(:'kept_ids'::jsonb)
          ),
          removed AS (
            DELETE FROM travel.vehicle_document document
            WHERE document.vehicle_id = :'vehicle_id'::uuid
              AND NOT EXISTS (SELECT 1 FROM kept WHERE kept.id = document.id)
            RETURNING id
          )
          SELECT jsonb_build_object('removed_count', count(*))::text FROM removed;
        """
        removed = run_psql_json(delete_sql, {"vehicle_id": vehicle_id, "kept_ids": json.dumps(kept_ids)}) or {}
        removed_count += int(removed.get("removed_count") or 0)

        for document in documents:
            if document.get("id") and not document.get("data_url"):
                continue
            parsed = parse_vehicle_document(document)
            if not parsed:
                skipped_count += 1
                continue

            vehicle_dir = ATTACHMENT_DIR / "vehicles" / vehicle_id
            vehicle_dir.mkdir(parents=True, exist_ok=True)
            stored_name = f"{parsed['client_id']}--{parsed['sha256'][:12]}--{safe_filename(parsed['file_name'])}"
            storage_key = f"vehicles/{vehicle_id}/{stored_name}"
            (vehicle_dir / stored_name).write_bytes(parsed["bytes"])

            insert_sql = """
              WITH saved AS (
                INSERT INTO travel.vehicle_document(
                  vehicle_id,
                  client_document_id,
                  document_kind,
                  file_name,
                  content_type,
                  byte_size,
                  storage_key,
                  sha256,
                  uploaded_by
                )
                VALUES (
                  :'vehicle_id'::uuid,
                  :'client_document_id',
                  :'document_kind',
                  :'file_name',
                  NULLIF(:'content_type', ''),
                  :'byte_size'::bigint,
                  :'storage_key',
                  :'sha256',
                  NULLIF(:'uploaded_by', '')::uuid
                )
                ON CONFLICT (vehicle_id, client_document_id)
                WHERE client_document_id IS NOT NULL
                DO UPDATE SET
                  document_kind = EXCLUDED.document_kind,
                  file_name = EXCLUDED.file_name,
                  content_type = EXCLUDED.content_type,
                  byte_size = EXCLUDED.byte_size,
                  storage_key = EXCLUDED.storage_key,
                  sha256 = EXCLUDED.sha256,
                  uploaded_by = EXCLUDED.uploaded_by,
                  uploaded_at = now()
                RETURNING id
              )
              SELECT jsonb_build_object('id', (SELECT id::text FROM saved))::text;
            """
            run_psql_json(
                insert_sql,
                {
                    "vehicle_id": vehicle_id,
                    "client_document_id": parsed["client_id"],
                    "document_kind": parsed["document_kind"],
                    "file_name": parsed["file_name"],
                    "content_type": parsed["content_type"],
                    "byte_size": len(parsed["bytes"]),
                    "storage_key": storage_key,
                    "sha256": parsed["sha256"],
                    "uploaded_by": uploader_id,
                },
            )
            saved_count += 1

    return {"saved_count": saved_count, "skipped_count": skipped_count, "removed_count": removed_count}


def normalize_vehicles(payload: dict) -> list[dict]:
    raw_vehicles = payload.get("vehicles")
    if not isinstance(raw_vehicles, list):
        raw_vehicles = []
        if any(
            str(payload.get(key) or "").strip()
            for key in ("vehicle_brand", "vehicle_plate", "vehicle_engine_volume", "vehicle_consumption")
        ):
            raw_vehicles.append(
                {
                    "id": payload.get("default_vehicle_id") or "",
                    "brand": payload.get("vehicle_brand") or "",
                    "plate": payload.get("vehicle_plate") or "",
                    "engine_volume": payload.get("vehicle_engine_volume") or "",
                    "fuel_type": payload.get("vehicle_fuel_type") or "ba95",
                    "consumption": payload.get("vehicle_consumption") or 0,
                    "secondary_fuel_type": payload.get("vehicle_secondary_fuel_type") or "",
                    "secondary_consumption": payload.get("vehicle_secondary_consumption") or 0,
                    "is_default": True,
                }
            )

    vehicles: list[dict] = []
    for raw in raw_vehicles:
        if not isinstance(raw, dict):
            continue

        brand = str(raw.get("brand") or "").strip()
        plate = str(raw.get("plate") or "").strip()
        engine_volume = integer_like(raw.get("engine_volume") or raw.get("engineVolume"))
        consumption = number_like(raw.get("consumption"))
        secondary_consumption = number_like(raw.get("secondary_consumption") or raw.get("secondaryConsumption"))
        documents = normalize_vehicle_documents(raw.get("documents"))
        if not any((brand, plate, engine_volume, documents, raw.get("consumption") not in (None, ""), raw.get("secondary_consumption") not in (None, ""), raw.get("secondaryConsumption") not in (None, ""))):
            continue

        fuel_type = str(raw.get("fuel_type") or raw.get("fuelType") or "ba95")
        if fuel_type not in FUEL_TYPES:
            fuel_type = "ba95"
        secondary_fuel_type = str(raw.get("secondary_fuel_type") or raw.get("secondaryFuelType") or "")
        if secondary_fuel_type not in FUEL_TYPES:
            secondary_fuel_type = ""

        vehicles.append(
            {
                "id": valid_uuid(raw.get("id")),
                "client_id": str(raw.get("client_id") or raw.get("clientId") or uuid.uuid4()).strip()[:80],
                "helios_id": str(raw.get("helios_id") or raw.get("heliosId") or "").strip(),
                "brand": brand,
                "plate": plate,
                "engine_volume": engine_volume,
                "fuel_type": fuel_type,
                "consumption": number_like(consumption),
                "secondary_fuel_type": secondary_fuel_type,
                "secondary_consumption": secondary_consumption if secondary_fuel_type else "0",
                "is_default": bool(raw.get("is_default") or raw.get("isDefault")),
                "documents": documents,
            }
        )

    if vehicles and not any(vehicle["is_default"] for vehicle in vehicles):
        vehicles[0]["is_default"] = True
    if vehicles:
        default_seen = False
        for vehicle in vehicles:
            if vehicle["is_default"] and not default_seen:
                default_seen = True
            elif vehicle["is_default"]:
                vehicle["is_default"] = False

    return vehicles


def normalize_vehicle_documents(raw_documents) -> list[dict]:
    if not isinstance(raw_documents, list):
        return []
    documents: list[dict] = []
    seen: set[str] = set()
    for raw in raw_documents[:10]:
        if not isinstance(raw, dict):
            continue
        document_id = valid_uuid(raw.get("id"))
        client_id = str(raw.get("clientDocumentId") or raw.get("client_document_id") or raw.get("clientId") or raw.get("id") or uuid.uuid4()).strip()
        client_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", client_id)[:80] or str(uuid.uuid4())
        dedupe_key = document_id or client_id
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        documents.append(
            {
                "id": document_id,
                "client_id": client_id,
                "document_kind": "otp" if str(raw.get("documentKind") or raw.get("document_kind") or "otp") == "otp" else "other",
                "file_name": str(raw.get("fileName") or raw.get("file_name") or raw.get("name") or "OTP").strip()[:180] or "OTP",
                "content_type": str(raw.get("contentType") or raw.get("content_type") or "").strip()[:100],
                "byte_size": int(float(number_like(raw.get("byteSize") or raw.get("byte_size")))),
                "data_url": str(raw.get("dataUrl") or raw.get("data_url") or "").strip(),
            }
        )
    return documents


def fetch_erp_employee(personal_number: str) -> dict | None:
    view = quote_mssql_identifier(ERP_USERS_VIEW)
    sql = f"""
      SET NOCOUNT ON;
      SELECT TOP (1) *
      FROM {view}
      WHERE CAST([Cislo] AS nvarchar(100)) = :'personal_number'
      FOR JSON PATH, WITHOUT_ARRAY_WRAPPER, INCLUDE_NULL_VALUES;
    """
    return run_sqlcmd_json(sql, {"personal_number": personal_number}) or None


def fetch_erp_vehicles(personal_number: str) -> list[dict]:
    view = quote_mssql_identifier(ERP_VEHICLES_VIEW)

    # Prefer direct row fetch to avoid JSON truncation from FOR JSON PATH
    try:
        import pyodbc
        conn_str = (
            "DRIVER={SQL Server};"
            f"SERVER={ERP_DB_SERVER};"
            f"DATABASE={ERP_DB_NAME};"
            f"UID={ERP_DB_USER};"
            f"PWD={ERP_DB_PASSWORD};"
        )
        with pyodbc.connect(conn_str, timeout=15) as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {view} WHERE CAST([CisloRidic] AS nvarchar(100)) = ?", personal_number)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception:
        pass

    try:
        import pymssql
        with pymssql.connect(
            server=ERP_DB_SERVER,
            user=ERP_DB_USER,
            password=ERP_DB_PASSWORD,
            database=ERP_DB_NAME,
            login_timeout=15,
            timeout=30,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {view} WHERE CAST([CisloRidic] AS nvarchar(100)) = %s", (personal_number,))
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as exc:
        raise ErpError(f"ERP vehicle query failed: {exc}") from exc
def quote_mssql_identifier(name: str) -> str:
    parts = [part for part in str(name or "").split(".") if part]
    if not parts:
        raise ErpError("ERP view name is not configured.")
    for part in parts:
        if not re.fullmatch(r"[A-Za-z0-9_]+", part):
            raise ErpError("ERP view name contains unsupported characters.")
    return ".".join(f"[{part}]" for part in parts)


def erp_employee_to_profile_payload(
    row: dict,
    personal_number: str,
    current_user: dict,
    current_profile: dict | None = None,
) -> dict:
    profile = current_profile or {}
    first_name = pick_erp_value(row, "Jmeno", "JmĂ©no", "KrestniJmeno", "KĹ™estnĂ­JmĂ©no")
    last_name = pick_erp_value(row, "Prijmeni", "PĹ™Ă­jmenĂ­")
    title_before = pick_erp_value(row, "TitulPred", "TitulPĹ™ed")
    title_after = pick_erp_value(row, "TitulZa")
    display_name = " ".join(part for part in (title_before, first_name, last_name, title_after) if part).strip()
    if not display_name:
        display_name = pick_erp_value(
            row,
            "PrijmeniJmenoTituly",
            "CeleJmeno",
            "CelĂ©JmĂ©no",
            "JmenoPrijmeni",
            "JmĂ©noPĹ™Ă­jmenĂ­",
            "Nazev",
            "NĂˇzev",
            "Zamestnanec",
            "ZamÄ›stnanec",
            "Pracovnik",
            "PracovnĂ­k",
        )

    organization_name = pick_erp_value(
        row,
        "Organizace",
        "Firma",
        "Spolecnost",
        "SpoleÄŤnost",
        "NazevOrganizace",
        "NĂˇzevOrganizace",
    )

    return {
        "display_name": display_name or current_user.get("display_name") or personal_number,
        "email": current_user.get("email") or profile.get("email") or "",
        "personal_number": personal_number,
        "address": format_erp_address(row),
        "phone": pick_erp_value(row, "Telefon", "Mobil", "Tel", "Phone"),
        "organization_name": organization_name or profile.get("organization_name") or "Oresi",
        "work_start": pick_erp_value(row, "PracovniDobaOd", "PracovnĂ­DobaOd", "WorkStart") or profile.get("work_start") or "08:00",
        "work_end": pick_erp_value(row, "PracovniDobaDo", "PracovnĂ­DobaDo", "WorkEnd") or profile.get("work_end") or "16:30",
        "cost_center_code": pick_erp_value(row, "Stredisko", "StĹ™edisko", "KodStrediska", "KĂłdStĹ™ediska", "CisloStrediska", "ÄŚĂ­sloStĹ™ediska"),
        "cost_center_name": pick_erp_value(row, "StrediskoNazev", "StĹ™ediskoNĂˇzev") or profile.get("cost_center_name") or "",
        "department_name": "",
        "default_transport_kind": profile.get("default_transport_kind") or "private_car",
        "helios_employee_id": pick_erp_value(row, "ID", "Id", "HeliosID", "HeliosId", "Cislo", "ÄŚĂ­slo") or personal_number,
        "helios_payload": row,
    }


def format_erp_address(row: dict) -> str:
    direct = pick_erp_value(row, "Adresa", "Bydliste", "BydliĹˇtÄ›")
    if direct:
        return direct
    parts = [
        pick_erp_value(row, "AdrTrvUliceSCisly", "AdrTrvUliceSÄŚĂ­sly", "Ulice"),
        pick_erp_value(row, "AdrTrvMisto", "AdrTrvMĂ­sto", "Mesto", "MÄ›sto", "Obec"),
        pick_erp_value(row, "AdrTrvPSC", "AdrTrvPSÄŚ", "PSC", "PSÄŚ", "Psc"),
        pick_erp_value(row, "AdrTrvZeme", "AdrTrvZemÄ›", "Zeme", "ZemÄ›"),
    ]
    return ", ".join(part for part in parts if part)


def erp_vehicle_to_payload(row: dict, personal_number: str, index: int) -> dict | None:
    plate = pick_erp_value(
        row,
        "SPZZobraz",
        "SPZVyhled",
        "EvCislo",
        "SPZ",
        "RZ",
        "RegistracniZnacka",
        "RegistraÄŤnĂ­ZnaÄŤka",
        "RegZnacka",
        "RegZnaÄŤka",
    )
    brand = pick_erp_value(row, "Popis", "Znacka", "ZnaÄŤka", "TovarniZnacka", "TovĂˇrnĂ­ZnaÄŤka", "Vozidlo", "Nazev", "NĂˇzev")
    vehicle_type = pick_erp_value(row, "TPTovZnacka", "Typ", "Model")
    if vehicle_type and vehicle_type not in brand:
        brand = " ".join(part for part in (brand, vehicle_type) if part)
    consumption = pick_erp_value(row, "NorPHML", "Spotreba", "SpotĹ™eba", "SpotrebaPHM", "SpotĹ™ebaPHM", "SpotrebaL")
    secondary_consumption = pick_erp_value(row, "NorPHMH", "Spotreba2", "SpotĹ™eba2", "SpotrebaEle", "SpotĹ™ebaEle", "SpotrebaKwh", "SpotĹ™ebaKwh")
    if not any((brand, plate, consumption, secondary_consumption)):
        return None

    fuel_type = fuel_type_from_erp(pick_erp_value(row, "Palivo", "DruhPHM", "PHM", "DruhPaliva", "idPHMKod"))
    secondary_fuel_type = fuel_type_from_erp(
        pick_erp_value(row, "DruhePalivo", "DruhĂ©Palivo", "DruhaEnergie", "DruhĂˇEnergie", "idPHMKodH"),
        default="",
    )
    if is_truthy_erp(row.get("Elektromobil")) and fuel_type != "electricity":
        secondary_fuel_type = "electricity"
    if not secondary_fuel_type and pick_erp_value(row, "AltPohon") not in ("", "0"):
        secondary_fuel_type = "other"

    helios_id = pick_erp_value(row, "ID", "Id", "HeliosID", "HeliosId", "CisloAuta", "ÄŚĂ­sloAuta", "Cislo", "ÄŚĂ­slo")
    if not helios_id:
        helios_id = f"{personal_number}:{plate or brand or index}"

    engine_volume = integer_like(pick_erp_value(row, "Obsah", "ObsahMotoru", "ObjemMotoru", "ZdvihovyObjem", "ZdvihovĂ˝Objem", "Objem"))
    if engine_volume == "0":
        engine_volume = ""

    return {
        "helios_id": helios_id,
        "brand": brand,
        "plate": plate,
        "engine_volume": engine_volume,
        "fuel_type": fuel_type,
        "consumption": number_like(consumption),
        "secondary_fuel_type": secondary_fuel_type,
        "secondary_consumption": number_like(secondary_consumption) if secondary_fuel_type and secondary_consumption else "0",
        "is_default": index == 0,
    }


def fuel_type_from_erp(value: object, default: str = "ba95") -> str:
    raw_text = str(value or "").strip()
    fuel_code_map = {
        "1": "ba95",
        "2": "diesel",
        "3": "other",
        "4": "electricity",
    }
    if raw_text in fuel_code_map:
        return fuel_code_map[raw_text]
    text = normalize_erp_key(raw_text)
    if not text:
        return default
    if any(token in text for token in ("elektr", "kwh", "ev")):
        return "electricity"
    if any(token in text for token in ("nafta", "diesel")):
        return "diesel"
    if "98" in text:
        return "ba98"
    if any(token in text for token in ("benzin", "benz", "natural", "95")):
        return "ba95"
    return "other"


def is_truthy_erp(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return normalize_erp_key(str(value or "")) in {"1", "true", "ano", "yes"}


def sync_erp_user_roles(user_id: str, employee_row: dict) -> dict:
    is_approver = is_truthy_erp(pick_erp_value(employee_row, "Schvalovatel"))
    if not is_approver:
        return {"approver_from_erp": False, "approver_role_added": False}

    sql = """
      WITH inserted AS (
        INSERT INTO travel.user_role(user_id, role_id)
        SELECT :'user_id'::uuid, role.id
        FROM travel.role role
        WHERE role.code = 'approver'
        ON CONFLICT DO NOTHING
        RETURNING user_id
      )
      SELECT jsonb_build_object(
        'approver_from_erp', true,
        'approver_role_added', EXISTS (SELECT 1 FROM inserted)
      )::text;
    """
    return run_psql_json(sql, {"user_id": user_id}) or {"approver_from_erp": True, "approver_role_added": False}


def save_erp_vehicles(user_id: str, vehicles: list[dict]) -> dict:
    normalized = normalize_vehicles({"vehicles": vehicles})
    if not normalized:
        return {"saved_count": 0}

    clear_defaults_sql = """
      WITH cleared AS (
        UPDATE travel.vehicle
        SET is_default = false,
            updated_at = now()
        WHERE owner_user_id = :'user_id'::uuid
          AND is_default
        RETURNING id
      )
      SELECT jsonb_build_object('cleared_default_count', (SELECT count(*) FROM cleared))::text;
    """
    clear_result = run_psql_json(clear_defaults_sql, {"user_id": user_id})

    upsert_sql = """
      WITH requested AS (
        SELECT
          NULLIF(vehicle.helios_id, '') AS helios_id,
          NULLIF(vehicle.brand, '') AS brand,
          NULLIF(vehicle.plate, '') AS plate,
          NULLIF(vehicle.engine_volume, '')::integer AS engine_volume_cc,
          COALESCE(NULLIF(vehicle.fuel_type, '')::travel.fuel_type, 'ba95') AS fuel_type,
          COALESCE(NULLIF(vehicle.consumption, '')::numeric, 0) AS consumption_l_per_100km,
          NULLIF(vehicle.secondary_fuel_type, '')::travel.fuel_type AS secondary_fuel_type,
          COALESCE(NULLIF(vehicle.secondary_consumption, '')::numeric, 0) AS secondary_consumption_per_100km,
          COALESCE(vehicle.is_default, false) AS is_default
        FROM jsonb_to_recordset(:'vehicles'::jsonb) AS vehicle(
          helios_id text,
          brand text,
          plate text,
          engine_volume text,
          fuel_type text,
          consumption text,
          secondary_fuel_type text,
          secondary_consumption text,
          is_default boolean
        )
      ),
      saved AS (
        INSERT INTO travel.vehicle(
          owner_user_id,
          brand,
          plate,
          engine_volume_cc,
          fuel_type,
          consumption_l_per_100km,
          secondary_fuel_type,
          secondary_consumption_per_100km,
          is_private,
          is_default,
          helios_id,
          source_system,
          helios_export_status,
          helios_exported_at,
          is_active
        )
        SELECT
          :'user_id'::uuid,
          brand,
          plate,
          engine_volume_cc,
          fuel_type,
          consumption_l_per_100km,
          secondary_fuel_type,
          secondary_consumption_per_100km,
          true,
          is_default,
          helios_id,
          'helios',
          'exported',
          now(),
          true
        FROM requested
        WHERE helios_id IS NOT NULL
        ON CONFLICT (helios_id) DO UPDATE
        SET owner_user_id = EXCLUDED.owner_user_id,
            brand = EXCLUDED.brand,
            plate = EXCLUDED.plate,
            engine_volume_cc = EXCLUDED.engine_volume_cc,
            fuel_type = EXCLUDED.fuel_type,
            consumption_l_per_100km = EXCLUDED.consumption_l_per_100km,
            secondary_fuel_type = EXCLUDED.secondary_fuel_type,
            secondary_consumption_per_100km = EXCLUDED.secondary_consumption_per_100km,
            is_private = EXCLUDED.is_private,
            is_default = EXCLUDED.is_default,
            source_system = CASE
              WHEN travel.vehicle.source_system = 'local' THEN 'mixed'::travel.user_source
              ELSE 'helios'::travel.user_source
            END,
            helios_export_status = 'exported'::travel.export_status,
            helios_exported_at = now(),
            helios_export_failed_at = NULL,
            helios_export_error = NULL,
            is_active = true,
            updated_at = now()
        RETURNING id, is_default
      ),
      profile_update AS (
        UPDATE travel.employee_profile
        SET default_vehicle_id = (SELECT id FROM saved WHERE is_default ORDER BY id LIMIT 1)
        WHERE user_id = :'user_id'::uuid
          AND EXISTS (SELECT 1 FROM saved WHERE is_default)
        RETURNING id
      )
      SELECT jsonb_build_object(
        'saved_count', (SELECT count(*) FROM saved),
        'default_vehicle_id', (SELECT id::text FROM saved WHERE is_default ORDER BY id LIMIT 1),
        'profile_updated', (SELECT count(*) FROM profile_update)
      )::text;
    """
    upsert_result = run_psql_json(upsert_sql, {"user_id": user_id, "vehicles": json.dumps(normalized)})
    return {**(clear_result or {}), **(upsert_result or {})}


def pick_erp_value(row: dict, *candidates: str) -> str:
    if not isinstance(row, dict):
        return ""
    normalized = {normalize_erp_key(key): value for key, value in row.items()}
    for candidate in candidates:
        value = normalized.get(normalize_erp_key(candidate))
        if value not in (None, ""):
            return str(value).strip()
    return ""


def normalize_erp_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(value or ""))
    ascii_only = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]", "", ascii_only.lower())


def normalize_approver_options(payload: dict) -> list[dict]:
    raw_options = payload.get("approver_options")
    if not isinstance(raw_options, list):
        raw_options = []
        legacy_default = valid_uuid(payload.get("default_approver_user_id"))
        if legacy_default:
            raw_options.append({"id": legacy_default, "is_default": True})

    options: list[dict] = []
    seen: set[str] = set()
    for raw in raw_options:
        if not isinstance(raw, dict):
            continue
        approver_id = valid_uuid(raw.get("id") or raw.get("approver_user_id"))
        if not approver_id or approver_id in seen:
            continue
        seen.add(approver_id)
        options.append(
            {
                "id": approver_id,
                "is_default": bool(raw.get("is_default") or raw.get("isDefault")),
            }
        )

    if options and not any(option["is_default"] for option in options):
        options[0]["is_default"] = True
    if options:
        default_seen = False
        for option in options:
            if option["is_default"] and not default_seen:
                default_seen = True
            elif option["is_default"]:
                option["is_default"] = False

    return options


def build_calculation_snapshot(order: dict, calc: dict) -> dict:
    attachments = []
    for attachment in order.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        currency_code = normalize_currency_code(attachment.get("currencyCode"))
        exchange_rate = "1" if currency_code == "CZK" else number_like(attachment.get("exchangeRate") or 1)
        attachments.append(
            {
                "id": attachment.get("id") or "",
                "fileName": attachment.get("fileName") or "",
                "contentType": attachment.get("contentType") or "",
                "byteSize": attachment.get("byteSize") or 0,
                "documentKind": attachment.get("documentKind") or "receipt",
                "expenseKind": attachment.get("expenseKind") or "other",
                "documentDate": attachment.get("documentDate") or "",
                "amount": number_like(attachment.get("amount")),
                "currencyCode": currency_code,
                "exchangeRate": exchange_rate,
                "amountCzk": number_like(attachment.get("amountCzk") or attachment_amount_czk({**attachment, "currencyCode": currency_code, "exchangeRate": exchange_rate})),
                "heliosExpenseCodeId": integer_like(attachment.get("heliosExpenseCodeId")),
                "heliosExpenseCodeLabel": attachment.get("heliosExpenseCodeLabel") or "",
                "description": attachment.get("description") or "",
            }
        )

    return {
        "calculation": calc or {},
        "order": {
            "employee": order.get("employee") or {},
            "trip": order.get("trip") or {},
            "approval": order.get("approval") or {},
            "vehicle": order.get("vehicle") or {},
            "routeLines": order.get("routeLines") or [],
            "attachments": attachments,
        },
    }


def save_order_attachments(travel_order_id: str, attachments: list[dict], user_id: str) -> dict:
    order_id = valid_uuid(travel_order_id)
    uploader_id = valid_uuid(user_id)
    if not order_id:
        return {"saved_count": 0, "skipped_count": len(attachments or [])}

    safe_items = []
    retained_items = []
    skipped = 0
    for raw in attachments[:30] if isinstance(attachments, list) else []:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        parsed = parse_attachment(raw)
        if parsed:
            safe_items.append(parsed)
            continue

        retained = parse_existing_attachment(raw)
        if retained:
            retained_items.append(retained)
            continue

        if not parsed:
            skipped += 1
            continue

    keep_attachment_ids = [item["attachment_id"] for item in retained_items if item["attachment_id"]]
    keep_client_ids = [item["client_id"] for item in retained_items if item["client_id"]]
    keep_client_ids.extend(item["client_id"] for item in safe_items if item["client_id"])

    delete_sql = """
      WITH keep_ids AS (
        SELECT value::uuid AS id
        FROM jsonb_array_elements_text(:'keep_attachment_ids'::jsonb)
        WHERE value ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
      ),
      keep_clients AS (
        SELECT value AS client_attachment_id
        FROM jsonb_array_elements_text(:'keep_client_ids'::jsonb)
        WHERE value <> ''
      ),
      removed AS (
        DELETE FROM travel.travel_attachment
        WHERE travel_order_id = :'travel_order_id'::uuid
          AND NOT EXISTS (
            SELECT 1
            FROM keep_ids
            WHERE keep_ids.id = travel.travel_attachment.id
          )
          AND NOT EXISTS (
            SELECT 1
            FROM keep_clients
            WHERE keep_clients.client_attachment_id = travel.travel_attachment.client_attachment_id
          )
        RETURNING id
      )
      SELECT jsonb_build_object('removed_count', count(*))::text FROM removed;
    """
    removed = run_psql_json(
        delete_sql,
        {
            "travel_order_id": order_id,
            "keep_attachment_ids": json.dumps(keep_attachment_ids),
            "keep_client_ids": json.dumps(keep_client_ids),
        },
    ) or {}

    for item in retained_items:
        update_existing_attachment(order_id, item)

    if not safe_items:
        return {"saved_count": 0, "retained_count": len(retained_items), "skipped_count": skipped, **removed}

    order_dir = ATTACHMENT_DIR / order_id
    order_dir.mkdir(parents=True, exist_ok=True)
    saved_count = 0

    for item in safe_items:
        stored_name = f"{item['client_id']}--{item['sha256'][:12]}--{safe_filename(item['file_name'])}"
        storage_key = f"{order_id}/{stored_name}"
        target = order_dir / stored_name
        target.write_bytes(item["bytes"])

        insert_sql = """
          WITH saved AS (
            INSERT INTO travel.travel_attachment(
              travel_order_id,
              client_attachment_id,
              document_kind,
              expense_kind,
              description,
              document_date,
              amount,
              currency_code,
              exchange_rate,
              amount_czk,
              helios_expense_code_id,
              helios_expense_code_label,
              file_name,
              content_type,
              byte_size,
              storage_key,
              sha256,
              uploaded_by
            )
            VALUES (
              :'travel_order_id'::uuid,
              :'client_attachment_id',
              :'document_kind',
              :'expense_kind',
              NULLIF(:'description', ''),
              NULLIF(:'document_date', '')::date,
              :'amount'::numeric,
              :'currency_code',
              :'exchange_rate'::numeric,
              :'amount_czk'::numeric,
              NULLIF(:'helios_expense_code_id', '')::integer,
              NULLIF(:'helios_expense_code_label', ''),
              :'file_name',
              NULLIF(:'content_type', ''),
              :'byte_size'::bigint,
              :'storage_key',
              :'sha256',
              NULLIF(:'uploaded_by', '')::uuid
            )
            ON CONFLICT (travel_order_id, client_attachment_id)
            WHERE client_attachment_id IS NOT NULL
            DO UPDATE SET
              document_kind = EXCLUDED.document_kind,
              expense_kind = EXCLUDED.expense_kind,
              description = EXCLUDED.description,
              document_date = EXCLUDED.document_date,
              amount = EXCLUDED.amount,
              currency_code = EXCLUDED.currency_code,
              exchange_rate = EXCLUDED.exchange_rate,
              amount_czk = EXCLUDED.amount_czk,
              helios_expense_code_id = EXCLUDED.helios_expense_code_id,
              helios_expense_code_label = EXCLUDED.helios_expense_code_label,
              file_name = EXCLUDED.file_name,
              content_type = EXCLUDED.content_type,
              byte_size = EXCLUDED.byte_size,
              storage_key = EXCLUDED.storage_key,
              sha256 = EXCLUDED.sha256,
              uploaded_by = EXCLUDED.uploaded_by,
              uploaded_at = now()
            RETURNING id
          )
          SELECT jsonb_build_object('id', (SELECT id::text FROM saved))::text;
        """
        run_psql_json(
            insert_sql,
            {
                "travel_order_id": order_id,
                "client_attachment_id": item["client_id"],
                "document_kind": item["document_kind"],
                "expense_kind": item["expense_kind"],
                "description": item["description"],
                "document_date": item["document_date"],
                "amount": item["amount"],
                "currency_code": item["currency_code"],
                "exchange_rate": item["exchange_rate"],
                "amount_czk": item["amount_czk"],
                "helios_expense_code_id": item["helios_expense_code_id"],
                "helios_expense_code_label": item["helios_expense_code_label"],
                "file_name": item["file_name"],
                "content_type": item["content_type"],
                "byte_size": len(item["bytes"]),
                "storage_key": storage_key,
                "sha256": item["sha256"],
                "uploaded_by": uploader_id,
            },
        )
        saved_count += 1

    return {"saved_count": saved_count, "retained_count": len(retained_items), "skipped_count": skipped, **removed}


def parse_existing_attachment(raw: dict) -> dict | None:
    attachment_id = valid_uuid(raw.get("id"))
    client_id = str(raw.get("clientAttachmentId") or "").strip()
    if not attachment_id and not client_id:
        return None

    document_kind = str(raw.get("documentKind") or "receipt").strip()
    if document_kind not in DOCUMENT_KINDS:
        document_kind = "other"
    expense_kind = str(raw.get("expenseKind") or raw.get("category") or "other").strip()
    if expense_kind not in EXPENSE_KINDS:
        expense_kind = "other"
    document_date = str(raw.get("documentDate") or "").strip()[:10]
    if document_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", document_date):
        document_date = ""
    currency_code = normalize_currency_code(raw.get("currencyCode") or raw.get("currency_code"))
    exchange_rate = "1" if currency_code == "CZK" else positive_number_like(raw.get("exchangeRate") or raw.get("exchange_rate"), 1)

    return {
        "attachment_id": attachment_id or "",
        "client_id": re.sub(r"[^a-zA-Z0-9_.-]+", "-", client_id)[:80],
        "document_kind": document_kind,
        "expense_kind": expense_kind,
        "description": str(raw.get("description") or "").strip()[:500],
        "document_date": document_date,
        "amount": number_like(raw.get("amount")),
        "currency_code": currency_code,
        "exchange_rate": exchange_rate,
        "amount_czk": attachment_amount_czk({**raw, "currencyCode": currency_code, "exchangeRate": exchange_rate}),
        "helios_expense_code_id": integer_like(raw.get("heliosExpenseCodeId") or raw.get("helios_expense_code_id")),
        "helios_expense_code_label": str(raw.get("heliosExpenseCodeLabel") or raw.get("helios_expense_code_label") or "").strip()[:100],
    }


def update_existing_attachment(travel_order_id: str, item: dict) -> None:
    sql = """
      WITH updated AS (
        UPDATE travel.travel_attachment
        SET document_kind = :'document_kind',
            expense_kind = :'expense_kind',
            description = NULLIF(:'description', ''),
            document_date = NULLIF(:'document_date', '')::date,
            amount = :'amount'::numeric,
            currency_code = :'currency_code',
            exchange_rate = :'exchange_rate'::numeric,
            amount_czk = :'amount_czk'::numeric,
            helios_expense_code_id = NULLIF(:'helios_expense_code_id', '')::integer,
            helios_expense_code_label = NULLIF(:'helios_expense_code_label', '')
        WHERE travel_order_id = :'travel_order_id'::uuid
          AND (
            (NULLIF(:'attachment_id', '')::uuid IS NOT NULL AND id = NULLIF(:'attachment_id', '')::uuid)
            OR (NULLIF(:'client_id', '') IS NOT NULL AND client_attachment_id = NULLIF(:'client_id', ''))
          )
        RETURNING id
      )
      SELECT jsonb_build_object('updated_count', count(*))::text FROM updated;
    """
    run_psql_json(
        sql,
        {
            "travel_order_id": travel_order_id,
            "attachment_id": item["attachment_id"],
            "client_id": item["client_id"],
            "document_kind": item["document_kind"],
            "expense_kind": item["expense_kind"],
            "description": item["description"],
            "document_date": item["document_date"],
            "amount": item["amount"],
            "currency_code": item["currency_code"],
            "exchange_rate": item["exchange_rate"],
            "amount_czk": item["amount_czk"],
            "helios_expense_code_id": item["helios_expense_code_id"],
            "helios_expense_code_label": item["helios_expense_code_label"],
        },
    )


def parse_attachment(raw: dict) -> dict | None:
    data_url = str(raw.get("dataUrl") or "").strip()
    if "," not in data_url:
        return None
    meta, encoded = data_url.split(",", 1)
    if ";base64" not in meta:
        return None

    try:
        content = base64.b64decode(encoded, validate=True)
    except Exception:
        return None

    if not content or len(content) > 10 * 1024 * 1024:
        return None

    file_name = str(raw.get("fileName") or raw.get("name") or "doklad").strip()[:180]
    if not file_name:
        file_name = "doklad"
    content_type = str(raw.get("contentType") or meta.removeprefix("data:").split(";")[0] or "").strip()[:100]
    document_kind = str(raw.get("documentKind") or "receipt").strip()
    if document_kind not in DOCUMENT_KINDS:
        document_kind = "other"
    expense_kind = str(raw.get("expenseKind") or raw.get("category") or "other").strip()
    if expense_kind not in EXPENSE_KINDS:
        expense_kind = "other"
    document_date = str(raw.get("documentDate") or "").strip()[:10]
    if document_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", document_date):
        document_date = ""
    currency_code = normalize_currency_code(raw.get("currencyCode") or raw.get("currency_code"))
    exchange_rate = "1" if currency_code == "CZK" else positive_number_like(raw.get("exchangeRate") or raw.get("exchange_rate"), 1)

    client_id = str(raw.get("id") or raw.get("clientAttachmentId") or uuid.uuid4()).strip()
    client_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", client_id)[:80] or str(uuid.uuid4())
    return {
        "client_id": client_id,
        "document_kind": document_kind,
        "expense_kind": expense_kind,
        "description": str(raw.get("description") or "").strip()[:500],
        "document_date": document_date,
        "amount": number_like(raw.get("amount")),
        "currency_code": currency_code,
        "exchange_rate": exchange_rate,
        "amount_czk": attachment_amount_czk({**raw, "currencyCode": currency_code, "exchangeRate": exchange_rate}),
        "helios_expense_code_id": integer_like(raw.get("heliosExpenseCodeId") or raw.get("helios_expense_code_id")),
        "helios_expense_code_label": str(raw.get("heliosExpenseCodeLabel") or raw.get("helios_expense_code_label") or "").strip()[:100],
        "file_name": file_name,
        "content_type": content_type,
        "bytes": content,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def parse_vehicle_document(raw: dict) -> dict | None:
    data_url = str(raw.get("data_url") or raw.get("dataUrl") or "").strip()
    if "," not in data_url:
        return None
    meta, encoded = data_url.split(",", 1)
    if ";base64" not in meta:
        return None

    try:
        content = base64.b64decode(encoded, validate=True)
    except Exception:
        return None

    if not content or len(content) > 10 * 1024 * 1024:
        return None

    file_name = str(raw.get("file_name") or raw.get("fileName") or raw.get("name") or "OTP").strip()[:180] or "OTP"
    content_type = str(raw.get("content_type") or raw.get("contentType") or meta.removeprefix("data:").split(";")[0] or "").strip()[:100]
    client_id = str(raw.get("client_id") or raw.get("clientDocumentId") or raw.get("id") or uuid.uuid4()).strip()
    client_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", client_id)[:80] or str(uuid.uuid4())
    document_kind = str(raw.get("document_kind") or raw.get("documentKind") or "otp")
    if document_kind not in {"otp", "other"}:
        document_kind = "otp"

    return {
        "client_id": client_id,
        "document_kind": document_kind,
        "file_name": file_name,
        "content_type": content_type,
        "bytes": content,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def safe_filename(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_. -]+", "-", value).strip(" .")
    return name[:120] or "doklad"


def valid_uuid(value) -> str:
    if not value:
        return ""
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return ""


def number_like(value) -> str:
    if value in (None, ""):
        return "0"
    try:
        return str(float(value))
    except (TypeError, ValueError):
        return "0"


def positive_number_like(value, fallback: float = 1.0) -> str:
    try:
        parsed = float(number_like(value))
    except (TypeError, ValueError):
        parsed = fallback
    if parsed <= 0:
        parsed = fallback
    return str(parsed)


def normalize_currency_code(value) -> str:
    code = str(value or "CZK").strip().upper()[:3]
    return code if re.fullmatch(r"[A-Z]{3}", code) else "CZK"


def ensure_unique_order_number(order_no: str, existing_order_id: str | None = None) -> str:
    desired = str(order_no or "").strip()
    year = str(datetime.now().year)
    if not desired:
        desired = f"CP-{year}-0001"

    conflict_sql = """
      SELECT to_jsonb(t)::text
      FROM (
        SELECT id::text AS id
        FROM travel.travel_order
        WHERE order_no = :'order_no'
        LIMIT 1
      ) t;
    """
    conflict = run_psql_json(conflict_sql, {"order_no": desired}) or {}
    conflict_id = str(conflict.get("id") or "")
    if not conflict_id:
        return desired
    if existing_order_id and conflict_id == str(existing_order_id):
        return desired

    next_sql = """
      SELECT to_jsonb(t)::text
      FROM (
        SELECT
          COALESCE(max((regexp_match(order_no, '^CP-' || :'year' || '-([0-9]+)$'))[1]::integer), 0) + 1 AS next_seq
        FROM travel.travel_order
        WHERE order_no ~ ('^CP-' || :'year' || '-[0-9]+$')
      ) t;
    """
    next_row = run_psql_json(next_sql, {"year": year}) or {"next_seq": 1}
    next_seq = int(next_row.get("next_seq") or 1)
    return f"CP-{year}-{next_seq:04d}"


def ensure_unique_request_number(request_no: str, existing_request_id: str | None = None) -> str:
    desired = str(request_no or "").strip()
    year = str(datetime.now().year)
    if not desired:
        desired = f"ZCP-{year}-0001"

    conflict_sql = """
      SELECT to_jsonb(t)::text
      FROM (
        SELECT id::text AS id
        FROM travel.travel_request
        WHERE request_no = :'request_no'
        LIMIT 1
      ) t;
    """
    conflict = run_psql_json(conflict_sql, {"request_no": desired}) or {}
    conflict_id = str(conflict.get("id") or "")
    if not conflict_id:
        return desired
    if existing_request_id and conflict_id == str(existing_request_id):
        return desired

    next_sql = """
      SELECT to_jsonb(t)::text
      FROM (
        SELECT
          COALESCE(max((regexp_match(request_no, '^ZCP-' || :'year' || '-([0-9]+)$'))[1]::integer), 0) + 1 AS next_seq
        FROM travel.travel_request
        WHERE request_no ~ ('^ZCP-' || :'year' || '-[0-9]+$')
      ) t;
    """
    next_row = run_psql_json(next_sql, {"year": year}) or {"next_seq": 1}
    next_seq = int(next_row.get("next_seq") or 1)
    return f"ZCP-{year}-{next_seq:04d}"


def get_user_contact(user_id: str) -> dict:
    sql = """
      SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
      FROM (
        SELECT id::text AS id, login_name::text AS login_name, email::text AS email, display_name
        FROM travel.app_user
        WHERE id = :'user_id'::uuid
        LIMIT 1
      ) t;
    """
    return run_psql_json(sql, {"user_id": user_id}) or {}


def attachment_amount_czk(raw: dict) -> str:
    amount = float(number_like(raw.get("amount")))
    explicit = raw.get("amountCzk") or raw.get("amount_czk")
    explicit_number = float(number_like(explicit))
    if explicit_number > 0:
        return str(round(explicit_number, 2))
    currency_code = normalize_currency_code(raw.get("currencyCode") or raw.get("currency_code"))
    exchange_rate = 1.0 if currency_code == "CZK" else float(positive_number_like(raw.get("exchangeRate") or raw.get("exchange_rate"), 1))
    return str(round(amount * exchange_rate, 2))


def integer_like(value) -> str:
    if value in (None, ""):
        return ""
    try:
        return str(max(0, int(float(value))))
    except (TypeError, ValueError):
        return ""


@app.get("/")
def index():
    return send_file(FRONTEND_DIR / "index.html")


@app.get("/<path:path>")
def static_files(path):
    target = FRONTEND_DIR / path
    if target.exists() and target.is_file():
        return send_from_directory(FRONTEND_DIR, path)
    return send_file(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    app.run(
        host=APP_HOST,
        port=APP_PORT,
        debug=os.environ.get("TRAVEL_DEBUG") == "1",
        use_reloader=False,
    )

# --- ERP fallback: use pyodbc when sqlcmd is missing (same approach as FakturaBotAI) ---
def run_sqlcmd_json(sql: str, variables: dict[str, object] | None = None):
    if not all((ERP_DB_SERVER, ERP_DB_NAME, ERP_DB_USER, ERP_DB_PASSWORD)):
        raise ErpError("ERP database connection is not configured.")

    rendered_sql = bind_mssql(sql, variables or {})

    sqlcmd_path = Path(SQLCMD)
    if sqlcmd_path.exists():
        command = [
            SQLCMD,
            "-S", ERP_DB_SERVER,
            "-d", ERP_DB_NAME,
            "-U", ERP_DB_USER,
            "-P", ERP_DB_PASSWORD,
            "-b", "-r", "1", "-w", "65535", "-y", "0", "-Y", "0",
        ]
        if ERP_DB_ENCRYPT:
            command.append("-N")
        result = subprocess.run(command + ["-Q", rendered_sql], capture_output=True, text=False, timeout=30)
        stdout = decode_command_output(result.stdout)
        stderr = decode_command_output(result.stderr)
        if result.returncode != 0:
            raise ErpError(stderr.strip() or "ERP database command failed.")
        raw_output = "".join(line.rstrip() for line in stdout.splitlines() if line.strip()).strip()
        starts = [i for i in (raw_output.find("{"), raw_output.find("[")) if i >= 0]
        if starts:
            start = min(starts)
            end = max(raw_output.rfind("}"), raw_output.rfind("]"))
            output = raw_output[start:end + 1]
        else:
            output = raw_output
        if not output:
            return None
        return json.loads(output)

    pyodbc_error = None
    try:
        import pyodbc
        conn_str = (
            "DRIVER={SQL Server};"
            f"SERVER={ERP_DB_SERVER};"
            f"DATABASE={ERP_DB_NAME};"
            f"UID={ERP_DB_USER};"
            f"PWD={ERP_DB_PASSWORD};"
        )
        with pyodbc.connect(conn_str, timeout=15) as conn:
            cursor = conn.cursor()
            cursor.execute(rendered_sql)
            row = cursor.fetchone()
    except Exception as exc:
        pyodbc_error = exc
        row = None

    if pyodbc_error is not None:
        try:
            import pymssql
            with pymssql.connect(
                server=ERP_DB_SERVER,
                user=ERP_DB_USER,
                password=ERP_DB_PASSWORD,
                database=ERP_DB_NAME,
                login_timeout=15,
                timeout=30,
            ) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SET TEXTSIZE 2147483647; " + rendered_sql)
                    row = cursor.fetchone()
        except Exception as pymssql_exc:
            raise ErpError(
                f"ERP query failed via pyodbc ({pyodbc_error}) and pymssql ({pymssql_exc})"
            ) from pymssql_exc

    if not row:
        return None
    output = row[0] if len(row) else None
    if not output:
        return None
    return json.loads(str(output))






def run_sqlcmd_json(sql: str, variables: dict[str, object] | None = None):
    if not all((ERP_DB_SERVER, ERP_DB_NAME, ERP_DB_USER, ERP_DB_PASSWORD)):
        raise ErpError("ERP database connection is not configured.")

    rendered_sql = bind_mssql(sql, variables or {})

    try:
        import pyodbc
        conn_str = (
            "DRIVER={SQL Server};"
            f"SERVER={ERP_DB_SERVER};"
            f"DATABASE={ERP_DB_NAME};"
            f"UID={ERP_DB_USER};"
            f"PWD={ERP_DB_PASSWORD};"
        )
        with pyodbc.connect(conn_str, timeout=15) as conn:
            cursor = conn.cursor()
            cursor.execute("SET TEXTSIZE 2147483647; " + rendered_sql)
            row = cursor.fetchone()
    except Exception as exc:
        raise ErpError(f"ERP pyodbc query failed: {exc}") from exc

    if not row:
        return None
    output = row[0] if len(row) else None
    if not output:
        return None
    return json.loads(str(output))





# ==== SMTP email hooks (submit + approval decision) ====
if "_EMAIL_HOOKS_INSTALLED" not in globals():
    _EMAIL_HOOKS_INSTALLED = True

    def _send_app_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:
        if not to_email:
            return False, "missing_recipient"
        if not SMTP_HOST:
            return False, "smtp_not_configured"
        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = SMTP_FROM
            msg["To"] = to_email
            msg.set_content(body)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
                if SMTP_TLS:
                    smtp.starttls()
                if SMTP_USER:
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def _get_user_contact(user_id: str) -> dict:
        sql = """
          SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
          FROM (
            SELECT id::text AS id, login_name::text AS login_name, email::text AS email, display_name
            FROM travel.app_user
            WHERE id = :'user_id'::uuid
            LIMIT 1
          ) t;
        """
        return run_psql_json(sql, {"user_id": user_id}) or {}

    def _get_order_owner_contact(travel_order_id: str) -> dict:
        sql = """
          SELECT COALESCE(to_jsonb(t), '{}'::jsonb)::text
          FROM (
            SELECT o.id::text AS travel_order_id, o.order_no, u.id::text AS user_id, u.email::text AS email, u.display_name
            FROM travel.travel_order o
            JOIN travel.app_user u ON u.id = o.owner_user_id
            WHERE o.id = :'travel_order_id'::uuid
            LIMIT 1
          ) t;
        """
        return run_psql_json(sql, {"travel_order_id": travel_order_id}) or {}

    def _app_base_url() -> str:
        base = (APP_BASE_URL or "").strip().rstrip("/")
        return base or request.url_root.rstrip("/")

    # wrap submit endpoint
    _orig_submit = app.view_functions.get("submit_travel_order")
    if _orig_submit:
        def _submit_with_email(*args, **kwargs):
            response = _orig_submit(*args, **kwargs)
            try:
                data = response.get_json(silent=True) if hasattr(response, "get_json") else None
                sub = (data or {}).get("submission") or {}
                approver_id = str(sub.get("approver_user_id") or "").strip()
                order_payload = request.get_json(silent=True) or {}
                order_no = str(((order_payload.get("order") or {}).get("number")) or sub.get("order_no") or "").strip()
                requester_name = (request.current_user or {}).get("display_name") or (request.current_user or {}).get("login_name") or "Uzivatel"

                if approver_id:
                    approver = _get_user_contact(approver_id)
                    to_email = str(approver.get("email") or "").strip()
                    approver_name = approver.get("display_name") or approver.get("login_name") or "Schvalovatel"
                    if to_email:
                        subject = f"cestovní příkaz ke schváleni: {order_no}"
                        body = (
                            f"Dobrý den, {approver_name},\n\n"
                            f"cestovní příkaz {order_no} čeká na vaše schválení.\n"
                            f"Zadal: {requester_name}\n\n"
                            f"Otevřít aplikaci: {_app_base_url()}/approvals\n"
                        )
                        sent, err = _send_app_email(to_email, subject, body)
                        if isinstance(sub, dict):
                            sub["emailApprovalRequestedSent"] = sent
                            if err and EMAIL_DEV_MODE:
                                sub["emailApprovalRequestedError"] = err
                            if isinstance(data, dict):
                                data["submission"] = sub
                                response = jsonify(data)
            except Exception:
                pass
            return response

        app.view_functions["submit_travel_order"] = _submit_with_email

    # wrap approval decision endpoint
    _orig_decision = app.view_functions.get("approval_decision")
    if _orig_decision:
        def _decision_with_email(*args, **kwargs):
            req_payload = request.get_json(silent=True) or {}
            action = str(req_payload.get("action") or "").strip()

            response = _orig_decision(*args, **kwargs)

            try:
                data = response.get_json(silent=True) if hasattr(response, "get_json") else None
                decision = (data or {}).get("decision") or {}
                order_id = str(decision.get("travel_order_id") or "").strip()
                order_no = str(decision.get("order_no") or "").strip()

                if order_id and action in {"approved", "returned", "rejected"}:
                    owner = _get_order_owner_contact(order_id)
                    to_email = str(owner.get("email") or "").strip()
                    owner_name = owner.get("display_name") or "Uzivatel"

                    if to_email:
                        action_map = {
                            "approved": "schválen",
                            "returned": "vrácen k doplnění",
                            "rejected": "zamítnut",
                        }
                        subject = f"Rozhodnutí o cestovním příkazu: {order_no}"
                        body = (
                            f"Dobrý den, {owner_name},\n\n"
                            f"vas cestovní příkaz {order_no} byl: {action_map.get(action, action)}.\n\n"
                            f"Otevřít aplikaci: {_app_base_url()}/\n"
                        )
                        sent, err = _send_app_email(to_email, subject, body)
                        if isinstance(decision, dict):
                            decision["emailDecisionSent"] = sent
                            if err and EMAIL_DEV_MODE:
                                decision["emailDecisionError"] = err
                            if isinstance(data, dict):
                                data["decision"] = decision
                                response = jsonify(data)
            except Exception:
                pass
            return response

        app.view_functions["approval_decision"] = _decision_with_email
# ==== end SMTP email hooks ====

