\set ON_ERROR_STOP on

WITH upsert_user AS (
  INSERT INTO travel.app_user(login_name, email, display_name, source_system)
  VALUES ('admin', 'admin@local', 'Lokální administrátor', 'local')
  ON CONFLICT (login_name) DO UPDATE
  SET email = EXCLUDED.email,
      display_name = EXCLUDED.display_name,
      is_active = true,
      source_system = 'local'
  RETURNING id
),
admin_role AS (
  SELECT id FROM travel.role WHERE code = 'admin'
),
employee_role AS (
  SELECT id FROM travel.role WHERE code = 'employee'
),
approver_role AS (
  SELECT id FROM travel.role WHERE code = 'approver'
)
INSERT INTO travel.local_auth_identity(user_id, password_hash, password_login_enabled)
SELECT id, crypt(:'app_admin_password', gen_salt('bf', 12)), true
FROM upsert_user
ON CONFLICT (user_id) DO UPDATE
SET password_hash = EXCLUDED.password_hash,
    password_changed_at = now(),
    password_login_enabled = true,
    failed_attempts = 0,
    locked_until = NULL;

INSERT INTO travel.user_role(user_id, role_id)
SELECT u.id, r.id
FROM travel.app_user u
JOIN travel.role r ON r.code IN ('admin', 'employee', 'approver', 'accountant')
WHERE u.login_name = 'admin'
ON CONFLICT DO NOTHING;
