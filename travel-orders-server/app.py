from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import uuid
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory


ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "travel-orders-app"
ATTACHMENT_DIR = ROOT / "travel-order-attachments"
PSQL = os.environ.get("TRAVEL_PSQL", r"C:\Program Files\PostgreSQL\18\bin\psql.exe")

DB_HOST = os.environ.get("TRAVEL_DB_HOST", "localhost")
DB_PORT = os.environ.get("TRAVEL_DB_PORT", "5432")
DB_NAME = os.environ.get("TRAVEL_DB_NAME", "travel_orders")
DB_USER = os.environ.get("TRAVEL_DB_USER", "postgres")
DB_PASSWORD = os.environ.get("TRAVEL_DB_PASSWORD")
APP_HOST = os.environ.get("TRAVEL_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("TRAVEL_PORT", "5055"))

TRANSPORT_KINDS = {"private_car", "company_car", "public_transport", "taxi", "plane", "other"}
FUEL_TYPES = {"ba95", "ba98", "diesel", "electricity", "other"}
DOCUMENT_KINDS = {"receipt", "invoice", "ticket", "other"}
EXPENSE_KINDS = {"fuel", "fare", "lodging", "parking", "meal", "other"}


app = Flask(__name__, static_folder=None)


class DatabaseError(RuntimeError):
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


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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


@app.errorhandler(DatabaseError)
def database_error(error):
    return jsonify({"error": "database_error", "message": str(error)}), 500


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
          'secondaryConsumption', COALESCE(v.secondary_consumption_per_100km, 0)
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
          AND (
            (SELECT count FROM option_count) = 0
            OR option.id IS NOT NULL
          )
      ) t;
    """
    return run_psql_json(sql, {"user_id": user_id}) or []


def is_approver_available(user_id: str, approver_user_id: str) -> bool:
    return any(approver.get("id") == approver_user_id for approver in get_user_approver_options(user_id))


def get_user_profile(user_id: str):
    sql = """
      SELECT jsonb_build_object(
        'id', u.id::text,
        'login_name', u.login_name::text,
        'display_name', u.display_name,
        'email', COALESCE(u.email::text, ''),
        'organization_name', COALESCE(ep.organization_name, ''),
        'personal_number', COALESCE(ep.personal_number, u.login_name::text),
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
    display_name = str(payload.get("display_name") or request.current_user.get("display_name") or "").strip()
    email = str(payload.get("email") or "").strip()
    personal_number = str(payload.get("personal_number") or request.current_user.get("login_name") or "").strip()
    default_transport_kind = str(payload.get("default_transport_kind") or "private_car")
    default_approver_user_id = valid_uuid(payload.get("default_approver_user_id"))
    if default_transport_kind not in TRANSPORT_KINDS:
        default_transport_kind = "private_car"
    if not display_name:
        return jsonify({"error": "missing_display_name"}), 400

    sql = """
      WITH updated_user AS (
        UPDATE travel.app_user u
        SET display_name = :'display_name',
            email = NULLIF(:'email', '')::citext,
            source_system = CASE
              WHEN u.source_system = 'helios' THEN 'mixed'::travel.user_source
              ELSE u.source_system
            END
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
          is_active
        )
        SELECT
          updated_user.id,
          COALESCE(NULLIF(:'personal_number', ''), updated_user.login_name::text),
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
        },
    )
    save_user_vehicles(user_id, normalize_vehicles(payload))
    if default_approver_user_id:
        try:
            save_user_default_approver(user_id, default_approver_user_id)
        except DatabaseError:
            return jsonify({"error": "approver_not_available"}), 400
    return jsonify({"profile": get_user_profile(user_id)})


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
          approval_request_id::text,
          travel_order_id::text,
          order_no,
          purpose,
          destination,
          requester_name,
          gross_amount,
          balance_rounded,
          requested_at,
          due_at,
          is_overdue
        FROM travel.v_approver_pending_orders
        WHERE approver_user_id = :'user_id'::uuid
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
                attachment.file_name AS "fileName",
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
      SELECT jsonb_build_object(
        'badge', COALESCE((SELECT to_jsonb(b) FROM (
          SELECT unread_count, failed_count
          FROM travel.v_user_notification_badge
          WHERE user_id = :'user_id'::uuid
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
          FROM travel.notification
          WHERE recipient_user_id = :'user_id'::uuid
          ORDER BY created_at DESC
          LIMIT 20
        ) n), '[]'::jsonb)
      )::text;
    """
    return jsonify(run_psql_json(sql, {"user_id": user_id}))


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
        return "unknown", "Monitor sazeb není inicializovaný."
    if not rate:
        return "missing", "Pro dnešní datum není v databázi aktivní sada sazeb."

    expected = monitor.get("latestKnownPayload") or {}
    expected_prices = expected.get("fuelPrices") or {}
    current_prices = rate.get("fuelPrices") or {}
    mismatches: list[str] = []

    expected_basic = number_like(expected.get("basicKmRate"))
    current_basic = number_like(rate.get("basicKmRate"))
    if float(expected_basic) and round(float(expected_basic), 2) != round(float(current_basic), 2):
        mismatches.append("základní náhrada Kč/km")

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
          jsonb_build_object('code', 'private_car', 'name', 'Vlastní vozidlo'),
          jsonb_build_object('code', 'company_car', 'name', 'Služební vozidlo'),
          jsonb_build_object('code', 'public_transport', 'name', 'Veřejná doprava'),
          jsonb_build_object('code', 'taxi', 'name', 'Taxi'),
          jsonb_build_object('code', 'plane', 'name', 'Letadlo'),
          jsonb_build_object('code', 'other', 'name', 'Jiné')
        ),
        'fuelTypes', jsonb_build_array(
          jsonb_build_object('code', 'ba95', 'name', 'Benzin 95'),
          jsonb_build_object('code', 'ba98', 'name', 'Benzin 98'),
          jsonb_build_object('code', 'diesel', 'name', 'Nafta'),
          jsonb_build_object('code', 'electricity', 'name', 'Elektřina'),
          jsonb_build_object('code', 'other', 'name', 'Jiné')
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


def save_admin_user(payload: dict):
    user_id = payload.get("id")
    login_name = str(payload.get("login_name") or payload.get("login") or "").strip()
    display_name = str(payload.get("display_name") or "").strip()
    email = str(payload.get("email") or "").strip() or None
    password = str(payload.get("password") or "")
    roles = payload.get("roles") or ["employee"]
    is_active = bool(payload.get("is_active", True))
    personal_number = str(payload.get("personal_number") or login_name).strip()
    default_transport_kind = str(payload.get("default_transport_kind") or "private_car")
    vehicles = normalize_vehicles(payload)
    approver_options = normalize_approver_options(payload)

    if default_transport_kind not in TRANSPORT_KINDS:
        default_transport_kind = "private_car"

    if not login_name or not display_name:
        return jsonify({"error": "missing_required_fields"}), 400

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
          :'personal_number',
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
        ON CONFLICT (personal_number) DO UPDATE
        SET user_id = EXCLUDED.user_id,
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


@app.post("/api/travel-orders/submit")
@require_auth
def submit_travel_order():
    payload = request.get_json(silent=True) or {}
    order = payload.get("order") or {}
    calc = payload.get("calculation") or {}
    order_no = str(order.get("number") or "").strip()
    if not order_no:
        return jsonify({"error": "missing_order_number"}), 400

    trip = order.get("trip") or {}
    approval = order.get("approval") or {}
    requested_approver_user_id = valid_uuid(approval.get("approverUserId"))
    if approval.get("approverUserId") and not requested_approver_user_id:
        return jsonify({"error": "invalid_approver"}), 400
    if requested_approver_user_id and not is_approver_available(request.current_user["user_id"], requested_approver_user_id):
        return jsonify({"error": "approver_not_available"}), 400
    lines = order.get("routeLines") or []
    sql = """
      WITH selected_approver AS (
        SELECT COALESCE(
          NULLIF(:'requested_approver_user_id', '')::uuid,
          (SELECT ep.default_approver_user_id FROM travel.employee_profile ep WHERE ep.user_id = :'owner_user_id'::uuid AND ep.default_approver_user_id IS NOT NULL),
          (SELECT u.id
           FROM travel.app_user u
           JOIN travel.user_role ur ON ur.user_id = u.id
           JOIN travel.role r ON r.id = ur.role_id AND r.code = 'approver'
           WHERE u.is_active AND u.id <> :'owner_user_id'::uuid
           ORDER BY u.display_name
           LIMIT 1),
          :'owner_user_id'::uuid
        ) AS approver_user_id
      ),
      rate AS (
        SELECT id FROM travel.legislation_rate_set WHERE code = 'CZ-2026' LIMIT 1
      ),
      saved_order AS (
        INSERT INTO travel.travel_order(
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
          rate_set_id,
          current_approver_user_id,
          submitted_at,
          export_status
        )
        VALUES (
          :'order_no',
          :'owner_user_id'::uuid,
          (SELECT id FROM travel.employee_profile WHERE user_id = :'owner_user_id'::uuid LIMIT 1),
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
          (SELECT id FROM rate),
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
            current_approver_user_id = EXCLUDED.current_approver_user_id,
            submitted_at = now()
        RETURNING id, order_no, current_approver_user_id
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
      saved_approval AS (
        INSERT INTO travel.approval_request(travel_order_id, step_no, approver_user_id, status, requested_at, due_at)
        VALUES ((SELECT id FROM saved_order), 1, (SELECT current_approver_user_id FROM saved_order), 'pending', now(), now() + interval '2 days')
        ON CONFLICT (travel_order_id, step_no, approver_user_id) DO UPDATE
        SET status = 'pending',
            requested_at = now(),
            due_at = now() + interval '2 days',
            decided_at = NULL,
            decision_comment = NULL
        RETURNING id
      ),
      saved_notification AS (
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
        VALUES (
          (SELECT current_approver_user_id FROM saved_order),
          'in_app',
          'queued',
          'approval_requested',
          'Nový cestovní příkaz ke schválení',
          'Cestovní příkaz ' || (SELECT order_no FROM saved_order) || ' čeká na schválení.',
          'travel_order',
          (SELECT id FROM saved_order),
          '/approvals'
        )
        RETURNING id
      )
      SELECT to_jsonb(t)::text
      FROM (
        SELECT
          (SELECT id::text FROM saved_order) AS travel_order_id,
          (SELECT id::text FROM saved_approval) AS approval_request_id,
          (SELECT current_approver_user_id::text FROM saved_order) AS approver_user_id,
          (SELECT id::text FROM saved_notification) AS notification_id
      ) t;
    """
    calc_lines = calc.get("lines") if isinstance(calc.get("lines"), list) else []
    lines_payload = []
    for index, line in enumerate(lines):
        line_calc = calc_lines[index] if index < len(calc_lines) and isinstance(calc_lines[index], dict) else {}
        lines_payload.append(
            {
                "start_at": line.get("startAt") or "",
                "from_place": line.get("from") or "",
                "to_place": line.get("to") or "",
                "end_at": line.get("endAt") or "",
                "company_or_place": line.get("company") or "",
                "purpose": line.get("purpose") or "",
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
                    "privateKmRate": number_like((order.get("vehicle") or {}).get("privateKmRate")),
                },
            }
        )
    snapshot = build_calculation_snapshot(order, calc)
    result = run_psql_json(
        sql,
        {
            "owner_user_id": request.current_user["user_id"],
            "requested_approver_user_id": requested_approver_user_id,
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
            order.get("attachments") or [],
            request.current_user["user_id"],
        )
    return jsonify({"submission": result})


@app.post("/api/approval-requests/<approval_request_id>/decision")
@require_auth
def approval_decision(approval_request_id):
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip()
    comment = str(payload.get("comment") or "").strip()
    if action not in {"approved", "returned", "rejected"}:
        return jsonify({"error": "invalid_action"}), 400

    status_map = {"approved": "approved", "returned": "draft", "rejected": "rejected"}
    note_map = {
        "approved": "Cestovní příkaz byl schválen.",
        "returned": "Cestovní příkaz byl vrácen k doplnění.",
        "rejected": "Cestovní příkaz byl zamítnut.",
    }
    sql = """
      WITH decided AS (
        UPDATE travel.approval_request ar
        SET status = :'action'::travel.approval_status,
            decided_at = now(),
            decision_comment = NULLIF(:'comment', '')
        WHERE ar.id = :'approval_request_id'::uuid
          AND ar.approver_user_id = :'approver_user_id'::uuid
          AND ar.status = 'pending'
        RETURNING ar.travel_order_id
      ),
      changed_order AS (
        UPDATE travel.travel_order o
        SET status = :'order_status'::travel.order_status,
            current_approver_user_id = CASE WHEN :'action' = 'approved' THEN NULL ELSE current_approver_user_id END,
            approved_at = CASE WHEN :'action' = 'approved' THEN now() ELSE approved_at END,
            rejected_at = CASE WHEN :'action' = 'rejected' THEN now() ELSE rejected_at END
        WHERE o.id = (SELECT travel_order_id FROM decided)
        RETURNING o.id, o.order_no, o.owner_user_id
      ),
      owner_notification AS (
        INSERT INTO travel.notification(recipient_user_id, channel, status, type_code, title, message, object_type, object_id, action_url)
        SELECT owner_user_id, 'in_app', 'queued', 'approval_decided', :'title', :'message' || ' (' || order_no || ')', 'travel_order', id, '/'
        FROM changed_order
        RETURNING id
      )
      SELECT to_jsonb(t)::text
      FROM (
        SELECT
          (SELECT id::text FROM changed_order) AS travel_order_id,
          (SELECT order_no FROM changed_order) AS order_no,
          (SELECT id::text FROM owner_notification) AS notification_id
      ) t;
    """
    result = run_psql_json(
        sql,
        {
            "approval_request_id": approval_request_id,
            "approver_user_id": request.current_user["user_id"],
            "action": action,
            "comment": comment,
            "order_status": status_map[action],
            "title": "Rozhodnutí o cestovním příkazu",
            "message": note_map[action],
        },
    )
    if not result.get("travel_order_id"):
        return jsonify({"error": "approval_not_found"}), 404
    return jsonify({"decision": result})


def save_user_default_approver(user_id: str, approver_user_id: str) -> dict:
    validate_sql = """
      WITH profile AS (
        SELECT id
        FROM travel.employee_profile
        WHERE user_id = :'user_id'::uuid
        LIMIT 1
      ),
      option_count AS (
        SELECT count(*) AS count
        FROM travel.employee_approver_option option
        WHERE option.employee_profile_id = (SELECT id FROM profile)
          AND option.is_active
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
      valid_requested AS (
        SELECT requested.approver_user_id, requested.is_default
        FROM requested
        JOIN travel.app_user approver ON approver.id = requested.approver_user_id AND approver.is_active
        JOIN travel.user_role ur ON ur.user_id = approver.id
        JOIN travel.role role ON role.id = ur.role_id AND role.code = 'approver'
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
          existing.id AS existing_id,
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
          COALESCE(existing_id, gen_random_uuid()),
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
      SELECT jsonb_build_object(
        'saved_count', (SELECT count(*) FROM saved),
        'default_vehicle_id', (SELECT id::text FROM saved WHERE is_default ORDER BY id LIMIT 1)
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

    return {
        **(deactivate_result or {}),
        **(clear_result or {}),
        **(upsert_result or {}),
        **(profile_result or {}),
    }


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
        if not any((brand, plate, engine_volume, raw.get("consumption") not in (None, ""), raw.get("secondary_consumption") not in (None, ""), raw.get("secondaryConsumption") not in (None, ""))):
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
                "brand": brand,
                "plate": plate,
                "engine_volume": engine_volume,
                "fuel_type": fuel_type,
                "consumption": number_like(consumption),
                "secondary_fuel_type": secondary_fuel_type,
                "secondary_consumption": secondary_consumption if secondary_fuel_type else "0",
                "is_default": bool(raw.get("is_default") or raw.get("isDefault")),
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
    skipped = 0
    for raw in attachments[:30] if isinstance(attachments, list) else []:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        parsed = parse_attachment(raw)
        if not parsed:
            skipped += 1
            continue
        safe_items.append(parsed)

    delete_sql = """
      WITH removed AS (
        DELETE FROM travel.travel_attachment
        WHERE travel_order_id = :'travel_order_id'::uuid
        RETURNING id
      )
      SELECT jsonb_build_object('removed_count', count(*))::text FROM removed;
    """
    removed = run_psql_json(delete_sql, {"travel_order_id": order_id}) or {}

    if not safe_items:
        return {"saved_count": 0, "skipped_count": skipped, **removed}

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
                "file_name": item["file_name"],
                "content_type": item["content_type"],
                "byte_size": len(item["bytes"]),
                "storage_key": storage_key,
                "sha256": item["sha256"],
                "uploaded_by": uploader_id,
            },
        )
        saved_count += 1

    return {"saved_count": saved_count, "skipped_count": skipped, **removed}


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

    client_id = str(raw.get("id") or raw.get("clientAttachmentId") or uuid.uuid4()).strip()
    client_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", client_id)[:80] or str(uuid.uuid4())
    return {
        "client_id": client_id,
        "document_kind": document_kind,
        "expense_kind": expense_kind,
        "description": str(raw.get("description") or "").strip()[:500],
        "document_date": document_date,
        "amount": number_like(raw.get("amount")),
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
