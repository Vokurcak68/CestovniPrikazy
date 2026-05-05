\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE SCHEMA IF NOT EXISTS travel;

DO $$ BEGIN CREATE TYPE travel.user_source AS ENUM ('local', 'helios', 'mixed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE travel.order_status AS ENUM ('draft', 'submitted', 'approved', 'settlement', 'closed', 'rejected', 'cancelled'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE travel.transport_kind AS ENUM ('private_car', 'company_car', 'public_transport', 'taxi', 'plane', 'other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE travel.route_segment_type AS ENUM ('private', 'domestic', 'foreign'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE travel.approval_status AS ENUM ('pending', 'approved', 'returned', 'rejected', 'cancelled', 'skipped'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE travel.notification_status AS ENUM ('queued', 'sent', 'read', 'failed', 'cancelled'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE travel.notification_channel AS ENUM ('in_app', 'email', 'webhook'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE travel.sync_status AS ENUM ('queued', 'running', 'succeeded', 'failed', 'partial'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE travel.export_status AS ENUM ('not_ready', 'ready', 'queued', 'exported', 'failed', 'cancelled'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE travel.fuel_type AS ENUM ('ba95', 'ba98', 'diesel', 'electricity', 'other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE OR REPLACE FUNCTION travel.touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS travel.app_user (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  login_name citext NOT NULL UNIQUE,
  email citext UNIQUE,
  display_name text NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  source_system travel.user_source NOT NULL DEFAULT 'local',
  helios_user_id text,
  helios_employee_id text,
  helios_personal_number text,
  helios_checksum text,
  last_synced_at timestamptz,
  sync_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_app_user_touch ON travel.app_user;
CREATE TRIGGER trg_app_user_touch
BEFORE UPDATE ON travel.app_user
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.role (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  description text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS travel.user_role (
  user_id uuid NOT NULL REFERENCES travel.app_user(id) ON DELETE CASCADE,
  role_id uuid NOT NULL REFERENCES travel.role(id) ON DELETE CASCADE,
  assigned_by uuid REFERENCES travel.app_user(id),
  assigned_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS travel.local_auth_identity (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL UNIQUE REFERENCES travel.app_user(id) ON DELETE CASCADE,
  password_hash text NOT NULL,
  password_changed_at timestamptz NOT NULL DEFAULT now(),
  password_login_enabled boolean NOT NULL DEFAULT true,
  failed_attempts integer NOT NULL DEFAULT 0,
  locked_until timestamptz,
  last_login_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_local_auth_identity_touch ON travel.local_auth_identity;
CREATE TRIGGER trg_local_auth_identity_touch
BEFORE UPDATE ON travel.local_auth_identity
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.auth_session (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES travel.app_user(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_ip inet,
  user_agent text
);

CREATE INDEX IF NOT EXISTS ix_auth_session_user_active
ON travel.auth_session(user_id, expires_at)
WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS travel.organization_unit (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  parent_id uuid REFERENCES travel.organization_unit(id),
  helios_id text UNIQUE,
  is_active boolean NOT NULL DEFAULT true,
  last_synced_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_organization_unit_touch ON travel.organization_unit;
CREATE TRIGGER trg_organization_unit_touch
BEFORE UPDATE ON travel.organization_unit
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.cost_center (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  organization_unit_id uuid REFERENCES travel.organization_unit(id),
  helios_id text UNIQUE,
  is_active boolean NOT NULL DEFAULT true,
  last_synced_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_cost_center_touch ON travel.cost_center;
CREATE TRIGGER trg_cost_center_touch
BEFORE UPDATE ON travel.cost_center
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.project_code (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  helios_id text UNIQUE,
  is_active boolean NOT NULL DEFAULT true,
  last_synced_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_project_code_touch ON travel.project_code;
CREATE TRIGGER trg_project_code_touch
BEFORE UPDATE ON travel.project_code
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.employee_profile (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid UNIQUE REFERENCES travel.app_user(id) ON DELETE SET NULL,
  personal_number text NOT NULL UNIQUE,
  first_name text,
  last_name text,
  title_before text,
  title_after text,
  display_name text NOT NULL,
  organization_name text,
  address text,
  phone text,
  email citext,
  work_start time NOT NULL DEFAULT '08:00',
  work_end time NOT NULL DEFAULT '16:30',
  cost_center_code text,
  cost_center_name text,
  department_name text,
  organization_unit_id uuid REFERENCES travel.organization_unit(id),
  cost_center_id uuid REFERENCES travel.cost_center(id),
  default_project_id uuid REFERENCES travel.project_code(id),
  default_transport_kind travel.transport_kind NOT NULL DEFAULT 'private_car',
  default_vehicle_id uuid,
  manager_user_id uuid REFERENCES travel.app_user(id),
  default_approver_user_id uuid REFERENCES travel.app_user(id),
  accountant_user_id uuid REFERENCES travel.app_user(id),
  helios_employee_id text UNIQUE,
  helios_payload jsonb,
  helios_checksum text,
  last_synced_at timestamptz,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_employee_profile_approvers
ON travel.employee_profile(default_approver_user_id, manager_user_id, accountant_user_id);

DROP TRIGGER IF EXISTS trg_employee_profile_touch ON travel.employee_profile;
CREATE TRIGGER trg_employee_profile_touch
BEFORE UPDATE ON travel.employee_profile
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.employee_approver_option (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_profile_id uuid NOT NULL REFERENCES travel.employee_profile(id) ON DELETE CASCADE,
  approver_user_id uuid NOT NULL REFERENCES travel.app_user(id) ON DELETE RESTRICT,
  is_default boolean NOT NULL DEFAULT false,
  source_system travel.user_source NOT NULL DEFAULT 'local',
  helios_id text,
  helios_payload jsonb,
  helios_checksum text,
  last_synced_at timestamptz,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (employee_profile_id, approver_user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_employee_approver_default
ON travel.employee_approver_option(employee_profile_id)
WHERE is_default AND is_active;

CREATE INDEX IF NOT EXISTS ix_employee_approver_option_approver
ON travel.employee_approver_option(approver_user_id)
WHERE is_active;

DROP TRIGGER IF EXISTS trg_employee_approver_option_touch ON travel.employee_approver_option;
CREATE TRIGGER trg_employee_approver_option_touch
BEFORE UPDATE ON travel.employee_approver_option
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.vehicle (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id uuid REFERENCES travel.app_user(id) ON DELETE SET NULL,
  brand text,
  plate text,
  engine_volume_cc integer,
  fuel_type travel.fuel_type NOT NULL DEFAULT 'ba95',
  consumption_l_per_100km numeric(10,3) NOT NULL DEFAULT 0,
  secondary_fuel_type travel.fuel_type,
  secondary_consumption_per_100km numeric(10,3) NOT NULL DEFAULT 0,
  is_private boolean NOT NULL DEFAULT true,
  is_default boolean NOT NULL DEFAULT false,
  helios_id text UNIQUE,
  source_system travel.user_source NOT NULL DEFAULT 'local',
  helios_export_status travel.export_status NOT NULL DEFAULT 'not_ready',
  helios_export_requested_at timestamptz,
  helios_exported_at timestamptz,
  helios_export_failed_at timestamptz,
  helios_export_error text,
  helios_export_travel_order_id uuid,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_vehicle_owner ON travel.vehicle(owner_user_id);

CREATE INDEX IF NOT EXISTS ix_vehicle_helios_export_status
ON travel.vehicle(helios_export_status, helios_export_requested_at)
WHERE is_active;

CREATE UNIQUE INDEX IF NOT EXISTS ux_vehicle_default_per_owner
ON travel.vehicle(owner_user_id)
WHERE is_default;

ALTER TABLE travel.employee_profile
  DROP CONSTRAINT IF EXISTS fk_employee_profile_default_vehicle;

ALTER TABLE travel.employee_profile
  ADD CONSTRAINT fk_employee_profile_default_vehicle
  FOREIGN KEY (default_vehicle_id) REFERENCES travel.vehicle(id) ON DELETE SET NULL;

DROP TRIGGER IF EXISTS trg_vehicle_touch ON travel.vehicle;
CREATE TRIGGER trg_vehicle_touch
BEFORE UPDATE ON travel.vehicle
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.legislation_rate_set (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  valid_from date NOT NULL,
  valid_to date,
  source_note text,
  regulation_no text,
  source_url text,
  published_at date,
  checked_at timestamptz,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE IF NOT EXISTS travel.legislation_rate_monitor (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  monitor_code text NOT NULL UNIQUE,
  name text NOT NULL,
  source_url text NOT NULL,
  latest_known_regulation_no text,
  latest_known_valid_from date,
  latest_known_payload jsonb,
  status text NOT NULL DEFAULT 'unknown',
  message text,
  last_checked_at timestamptz,
  next_check_after date,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_legislation_rate_monitor_touch ON travel.legislation_rate_monitor;
CREATE TRIGGER trg_legislation_rate_monitor_touch
BEFORE UPDATE ON travel.legislation_rate_monitor
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.domestic_meal_rate (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rate_set_id uuid NOT NULL REFERENCES travel.legislation_rate_set(id) ON DELETE CASCADE,
  band_code text NOT NULL,
  hours_from numeric(6,2) NOT NULL,
  hours_to numeric(6,2),
  amount numeric(12,2) NOT NULL,
  reduction_percent_per_free_meal numeric(5,2) NOT NULL,
  UNIQUE (rate_set_id, band_code),
  CHECK (hours_to IS NULL OR hours_to > hours_from)
);

CREATE TABLE IF NOT EXISTS travel.fuel_price_rate (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rate_set_id uuid NOT NULL REFERENCES travel.legislation_rate_set(id) ON DELETE CASCADE,
  fuel_type travel.fuel_type NOT NULL,
  price_per_unit numeric(12,2) NOT NULL,
  unit text NOT NULL DEFAULT 'l',
  UNIQUE (rate_set_id, fuel_type)
);

CREATE TABLE IF NOT EXISTS travel.km_compensation_rate (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rate_set_id uuid NOT NULL REFERENCES travel.legislation_rate_set(id) ON DELETE CASCADE,
  vehicle_kind text NOT NULL DEFAULT 'passenger_car',
  amount_per_km numeric(12,2) NOT NULL,
  UNIQUE (rate_set_id, vehicle_kind)
);

CREATE TABLE IF NOT EXISTS travel.travel_order (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  order_no text NOT NULL UNIQUE,
  owner_user_id uuid NOT NULL REFERENCES travel.app_user(id),
  employee_profile_id uuid REFERENCES travel.employee_profile(id),
  status travel.order_status NOT NULL DEFAULT 'draft',
  purpose text,
  destination text,
  visited_companies text,
  companions text,
  planned_start_at timestamptz,
  planned_end_at timestamptz,
  report_date date,
  expected_expense numeric(14,2) NOT NULL DEFAULT 0,
  advance_amount numeric(14,2) NOT NULL DEFAULT 0,
  currency_code char(3) NOT NULL DEFAULT 'CZK',
  cost_center_id uuid REFERENCES travel.cost_center(id),
  project_id uuid REFERENCES travel.project_code(id),
  rate_set_id uuid REFERENCES travel.legislation_rate_set(id),
  current_approver_user_id uuid REFERENCES travel.app_user(id),
  submitted_at timestamptz,
  approved_at timestamptz,
  settlement_opened_at timestamptz,
  closed_at timestamptz,
  rejected_at timestamptz,
  export_status travel.export_status NOT NULL DEFAULT 'not_ready',
  helios_document_id text,
  helios_export_payload jsonb,
  helios_exported_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_travel_order_owner_status ON travel.travel_order(owner_user_id, status);
CREATE INDEX IF NOT EXISTS ix_travel_order_approver_status ON travel.travel_order(current_approver_user_id, status);
CREATE INDEX IF NOT EXISTS ix_travel_order_status_updated ON travel.travel_order(status, updated_at DESC);

ALTER TABLE travel.vehicle
  DROP CONSTRAINT IF EXISTS fk_vehicle_helios_export_travel_order;

ALTER TABLE travel.vehicle
  ADD CONSTRAINT fk_vehicle_helios_export_travel_order
  FOREIGN KEY (helios_export_travel_order_id) REFERENCES travel.travel_order(id) ON DELETE SET NULL;

DROP TRIGGER IF EXISTS trg_travel_order_touch ON travel.travel_order;
CREATE TRIGGER trg_travel_order_touch
BEFORE UPDATE ON travel.travel_order
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.travel_route_line (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  travel_order_id uuid NOT NULL REFERENCES travel.travel_order(id) ON DELETE CASCADE,
  sequence_no integer NOT NULL,
  start_at timestamptz,
  from_place text,
  to_place text,
  end_at timestamptz,
  company_or_place text,
  purpose text,
  segment_type travel.route_segment_type NOT NULL DEFAULT 'domestic',
  foreign_country_code text,
  foreign_country_name text,
  foreign_meal_currency char(3),
  foreign_meal_rate numeric(14,2),
  foreign_exchange_rate numeric(14,6),
  foreign_exchange_rate_date date,
  foreign_meal_amount_czk numeric(14,2),
  transport_kind travel.transport_kind NOT NULL DEFAULT 'private_car',
  vehicle_id uuid REFERENCES travel.vehicle(id),
  km numeric(12,2) NOT NULL DEFAULT 0,
  fare_amount numeric(14,2) NOT NULL DEFAULT 0,
  lodging_amount numeric(14,2) NOT NULL DEFAULT 0,
  other_amount numeric(14,2) NOT NULL DEFAULT 0,
  free_meals integer NOT NULL DEFAULT 0,
  calculated_hours numeric(10,2) NOT NULL DEFAULT 0,
  calculated_meal_amount numeric(14,2) NOT NULL DEFAULT 0,
  calculated_private_vehicle_amount numeric(14,2) NOT NULL DEFAULT 0,
  calculated_total_amount numeric(14,2) NOT NULL DEFAULT 0,
  calculation_detail jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (travel_order_id, sequence_no),
  CHECK (free_meals BETWEEN 0 AND 3)
);

CREATE INDEX IF NOT EXISTS ix_travel_route_line_order ON travel.travel_route_line(travel_order_id, sequence_no);

DROP TRIGGER IF EXISTS trg_travel_route_line_touch ON travel.travel_route_line;
CREATE TRIGGER trg_travel_route_line_touch
BEFORE UPDATE ON travel.travel_route_line
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.travel_order_total (
  travel_order_id uuid PRIMARY KEY REFERENCES travel.travel_order(id) ON DELETE CASCADE,
  total_km numeric(14,2) NOT NULL DEFAULT 0,
  total_hours numeric(14,2) NOT NULL DEFAULT 0,
  transport_amount numeric(14,2) NOT NULL DEFAULT 0,
  meal_amount numeric(14,2) NOT NULL DEFAULT 0,
  lodging_amount numeric(14,2) NOT NULL DEFAULT 0,
  other_amount numeric(14,2) NOT NULL DEFAULT 0,
  gross_amount numeric(14,2) NOT NULL DEFAULT 0,
  advance_amount numeric(14,2) NOT NULL DEFAULT 0,
  balance_amount numeric(14,2) NOT NULL DEFAULT 0,
  balance_rounded numeric(14,2) NOT NULL DEFAULT 0,
  calculation_snapshot jsonb,
  calculated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS travel.travel_attachment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  travel_order_id uuid NOT NULL REFERENCES travel.travel_order(id) ON DELETE CASCADE,
  route_line_id uuid REFERENCES travel.travel_route_line(id) ON DELETE SET NULL,
  client_attachment_id text,
  document_kind text NOT NULL DEFAULT 'receipt',
  expense_kind text NOT NULL DEFAULT 'other',
  description text,
  document_date date,
  amount numeric(14,2),
  currency_code char(3) NOT NULL DEFAULT 'CZK',
  exchange_rate numeric(14,6) NOT NULL DEFAULT 1,
  amount_czk numeric(14,2),
  helios_expense_code_id integer,
  helios_expense_code_label text,
  file_name text NOT NULL,
  content_type text,
  byte_size bigint,
  storage_key text NOT NULL,
  sha256 text,
  uploaded_by uuid REFERENCES travel.app_user(id),
  uploaded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_travel_attachment_order ON travel.travel_attachment(travel_order_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_travel_attachment_client
ON travel.travel_attachment(travel_order_id, client_attachment_id)
WHERE client_attachment_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS travel.approval_rule (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  cost_center_id uuid REFERENCES travel.cost_center(id),
  amount_from numeric(14,2),
  amount_to numeric(14,2),
  priority integer NOT NULL DEFAULT 100,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (amount_to IS NULL OR amount_from IS NULL OR amount_to >= amount_from)
);

DROP TRIGGER IF EXISTS trg_approval_rule_touch ON travel.approval_rule;
CREATE TRIGGER trg_approval_rule_touch
BEFORE UPDATE ON travel.approval_rule
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

CREATE TABLE IF NOT EXISTS travel.approval_rule_step (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  approval_rule_id uuid NOT NULL REFERENCES travel.approval_rule(id) ON DELETE CASCADE,
  step_no integer NOT NULL,
  approver_user_id uuid REFERENCES travel.app_user(id),
  approver_role_code text,
  approver_from_employee_field text,
  due_after interval NOT NULL DEFAULT interval '2 days',
  is_required boolean NOT NULL DEFAULT true,
  UNIQUE (approval_rule_id, step_no),
  CHECK (
    approver_user_id IS NOT NULL
    OR approver_role_code IS NOT NULL
    OR approver_from_employee_field IN ('manager_user_id', 'default_approver_user_id', 'accountant_user_id')
  )
);

CREATE TABLE IF NOT EXISTS travel.approval_request (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  travel_order_id uuid NOT NULL REFERENCES travel.travel_order(id) ON DELETE CASCADE,
  step_no integer NOT NULL,
  approver_user_id uuid NOT NULL REFERENCES travel.app_user(id),
  status travel.approval_status NOT NULL DEFAULT 'pending',
  requested_at timestamptz NOT NULL DEFAULT now(),
  due_at timestamptz,
  decided_at timestamptz,
  decision_comment text,
  notification_id uuid,
  UNIQUE (travel_order_id, step_no, approver_user_id)
);

CREATE INDEX IF NOT EXISTS ix_approval_request_approver_pending
ON travel.approval_request(approver_user_id, due_at)
WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS travel.notification (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recipient_user_id uuid NOT NULL REFERENCES travel.app_user(id) ON DELETE CASCADE,
  channel travel.notification_channel NOT NULL DEFAULT 'in_app',
  status travel.notification_status NOT NULL DEFAULT 'queued',
  type_code text NOT NULL,
  title text NOT NULL,
  message text,
  object_type text,
  object_id uuid,
  action_url text,
  scheduled_for timestamptz NOT NULL DEFAULT now(),
  sent_at timestamptz,
  read_at timestamptz,
  failed_at timestamptz,
  failure_message text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_notification_recipient_status
ON travel.notification(recipient_user_id, status, scheduled_for DESC);

ALTER TABLE travel.approval_request
  DROP CONSTRAINT IF EXISTS fk_approval_request_notification;
ALTER TABLE travel.approval_request
  ADD CONSTRAINT fk_approval_request_notification
  FOREIGN KEY (notification_id) REFERENCES travel.notification(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS travel.travel_comment (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  travel_order_id uuid NOT NULL REFERENCES travel.travel_order(id) ON DELETE CASCADE,
  author_user_id uuid REFERENCES travel.app_user(id) ON DELETE SET NULL,
  comment_text text NOT NULL,
  is_internal boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS travel.audit_log (
  id bigserial PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_user_id uuid REFERENCES travel.app_user(id) ON DELETE SET NULL,
  entity_schema text NOT NULL DEFAULT 'travel',
  entity_table text NOT NULL,
  entity_id uuid,
  action text NOT NULL,
  old_data jsonb,
  new_data jsonb,
  request_id text
);

CREATE INDEX IF NOT EXISTS ix_audit_log_entity ON travel.audit_log(entity_table, entity_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS travel.helios_sync_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type text NOT NULL,
  status travel.sync_status NOT NULL DEFAULT 'queued',
  started_at timestamptz,
  finished_at timestamptz,
  requested_by uuid REFERENCES travel.app_user(id),
  source_system text NOT NULL DEFAULT 'helios',
  items_read integer NOT NULL DEFAULT 0,
  items_inserted integer NOT NULL DEFAULT 0,
  items_updated integer NOT NULL DEFAULT 0,
  items_deactivated integer NOT NULL DEFAULT 0,
  error_message text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS travel.helios_entity_map (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  local_table text NOT NULL,
  local_id uuid NOT NULL,
  helios_entity text NOT NULL,
  helios_id text NOT NULL,
  helios_checksum text,
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  last_payload jsonb,
  UNIQUE (local_table, local_id, helios_entity),
  UNIQUE (helios_entity, helios_id)
);

CREATE TABLE IF NOT EXISTS travel.helios_export_queue (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  travel_order_id uuid NOT NULL REFERENCES travel.travel_order(id) ON DELETE CASCADE,
  status travel.export_status NOT NULL DEFAULT 'queued',
  payload jsonb NOT NULL,
  attempt_count integer NOT NULL DEFAULT 0,
  last_attempt_at timestamptz,
  exported_at timestamptz,
  helios_document_id text,
  error_message text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_helios_export_queue_status
ON travel.helios_export_queue(status, created_at);

CREATE OR REPLACE FUNCTION travel.authenticate_local(p_login text, p_password text)
RETURNS TABLE (
  user_id uuid,
  login_name citext,
  email citext,
  display_name text,
  roles text[]
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = travel, public
AS $$
DECLARE
  v_identity travel.local_auth_identity%ROWTYPE;
  v_ok boolean;
BEGIN
  SELECT i.*
  INTO v_identity
  FROM travel.local_auth_identity i
  JOIN travel.app_user u ON u.id = i.user_id
  WHERE u.is_active
    AND i.password_login_enabled
    AND (u.login_name = p_login::citext OR u.email = p_login::citext)
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN;
  END IF;

  IF v_identity.locked_until IS NOT NULL AND v_identity.locked_until > now() THEN
    RETURN;
  END IF;

  v_ok := v_identity.password_hash = crypt(p_password, v_identity.password_hash);

  IF NOT v_ok THEN
    UPDATE travel.local_auth_identity
    SET failed_attempts = failed_attempts + 1,
        locked_until = CASE WHEN failed_attempts + 1 >= 5 THEN now() + interval '15 minutes' ELSE locked_until END
    WHERE id = v_identity.id;
    RETURN;
  END IF;

  UPDATE travel.local_auth_identity
  SET failed_attempts = 0,
      locked_until = NULL,
      last_login_at = now()
  WHERE id = v_identity.id;

  RETURN QUERY
  SELECT u.id,
         u.login_name,
         u.email,
         u.display_name,
         COALESCE(array_agg(r.code ORDER BY r.code) FILTER (WHERE r.code IS NOT NULL), ARRAY[]::text[])
  FROM travel.app_user u
  LEFT JOIN travel.user_role ur ON ur.user_id = u.id
  LEFT JOIN travel.role r ON r.id = ur.role_id
  WHERE u.id = v_identity.user_id
  GROUP BY u.id, u.login_name, u.email, u.display_name;
END;
$$;

CREATE OR REPLACE VIEW travel.v_approver_pending_orders AS
SELECT
  ar.approver_user_id,
  ar.id AS approval_request_id,
  ar.travel_order_id,
  o.order_no,
  o.status AS order_status,
  o.purpose,
  o.destination,
  requester.display_name AS requester_name,
  totals.gross_amount,
  totals.balance_rounded,
  ar.requested_at,
  ar.due_at,
  (ar.due_at IS NOT NULL AND ar.due_at < now()) AS is_overdue
FROM travel.approval_request ar
JOIN travel.travel_order o ON o.id = ar.travel_order_id
JOIN travel.app_user requester ON requester.id = o.owner_user_id
LEFT JOIN travel.travel_order_total totals ON totals.travel_order_id = o.id
WHERE ar.status = 'pending'
  AND o.owner_user_id <> ar.approver_user_id;

CREATE OR REPLACE VIEW travel.v_approver_dashboard AS
SELECT
  approver_user_id,
  count(*) AS pending_count,
  count(*) FILTER (WHERE is_overdue) AS overdue_count,
  min(requested_at) AS oldest_requested_at,
  min(due_at) FILTER (WHERE due_at IS NOT NULL) AS nearest_due_at,
  COALESCE(sum(gross_amount), 0) AS pending_gross_amount
FROM travel.v_approver_pending_orders
GROUP BY approver_user_id;

CREATE OR REPLACE VIEW travel.v_user_notification_badge AS
SELECT
  recipient_user_id AS user_id,
  count(*) FILTER (WHERE status IN ('queued', 'sent') AND read_at IS NULL) AS unread_count,
  count(*) FILTER (WHERE status = 'failed') AS failed_count
FROM travel.notification
GROUP BY recipient_user_id;

INSERT INTO travel.role(code, name, description) VALUES
  ('admin', 'Administrátor', 'Správa aplikace, uživatelů a sazeb'),
  ('employee', 'Zaměstnanec', 'Zadávání vlastních cestovních příkazů'),
  ('approver', 'Schvalovatel', 'Schvalování cestovních příkazů'),
  ('accountant', 'Účetní', 'Kontrola, uzavření a export do účetnictví')
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description;

INSERT INTO travel.legislation_rate_set(code, name, valid_from, source_note, regulation_no, source_url, published_at, checked_at) VALUES
  (
    'CZ-2026',
    'Tuzemské cestovní náhrady 2026',
    DATE '2026-01-01',
    'Sazby dle vyhlášky MPSV pro tuzemské cestovní náhrady.',
    '573/2025 Sb.',
    'https://ppropo.mpsv.cz/Vyhlaska_573_2025',
    DATE '2025-12-18',
    now()
  )
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    valid_from = EXCLUDED.valid_from,
    source_note = EXCLUDED.source_note,
    regulation_no = EXCLUDED.regulation_no,
    source_url = EXCLUDED.source_url,
    published_at = EXCLUDED.published_at,
    checked_at = now();

INSERT INTO travel.legislation_rate_monitor(
  monitor_code,
  name,
  source_url,
  latest_known_regulation_no,
  latest_known_valid_from,
  latest_known_payload,
  status,
  message,
  last_checked_at,
  next_check_after
)
VALUES (
  'CZ_TRAVEL_RATES',
  'Tuzemské cestovní náhrady',
  'https://ppropo.mpsv.cz/Vyhlaska_573_2025',
  '573/2025 Sb.',
  DATE '2026-01-01',
  '{"basicKmRate":5.90,"fuelPrices":{"ba95":34.70,"ba98":39.00,"diesel":34.10,"electricity":7.20},"source":"MPSV vyhláška 573/2025 Sb."}'::jsonb,
  'ok',
  'Lokální sazby odpovídají známé vyhlášce pro rok 2026. Mimořádné změny se sledují vložením nové sazby s novou účinností.',
  now(),
  DATE '2026-12-01'
)
ON CONFLICT (monitor_code) DO UPDATE
SET latest_known_regulation_no = EXCLUDED.latest_known_regulation_no,
    latest_known_valid_from = EXCLUDED.latest_known_valid_from,
    latest_known_payload = EXCLUDED.latest_known_payload,
    status = EXCLUDED.status,
    message = EXCLUDED.message,
    last_checked_at = now(),
    next_check_after = EXCLUDED.next_check_after,
    source_url = EXCLUDED.source_url;

WITH rs AS (
  SELECT id FROM travel.legislation_rate_set WHERE code = 'CZ-2026'
)
INSERT INTO travel.domestic_meal_rate(rate_set_id, band_code, hours_from, hours_to, amount, reduction_percent_per_free_meal)
SELECT id, '5_12', 5, 12, 155, 70 FROM rs
UNION ALL SELECT id, '12_18', 12, 18, 236, 35 FROM rs
UNION ALL SELECT id, '18_plus', 18, NULL, 370, 25 FROM rs
ON CONFLICT (rate_set_id, band_code) DO UPDATE
SET hours_from = EXCLUDED.hours_from,
    hours_to = EXCLUDED.hours_to,
    amount = EXCLUDED.amount,
    reduction_percent_per_free_meal = EXCLUDED.reduction_percent_per_free_meal;

WITH rs AS (
  SELECT id FROM travel.legislation_rate_set WHERE code = 'CZ-2026'
)
INSERT INTO travel.fuel_price_rate(rate_set_id, fuel_type, price_per_unit, unit)
SELECT id, 'ba95'::travel.fuel_type, 34.70, 'l' FROM rs
UNION ALL SELECT id, 'ba98'::travel.fuel_type, 39.00, 'l' FROM rs
UNION ALL SELECT id, 'diesel'::travel.fuel_type, 34.10, 'l' FROM rs
UNION ALL SELECT id, 'electricity'::travel.fuel_type, 7.20, 'kWh' FROM rs
ON CONFLICT (rate_set_id, fuel_type) DO UPDATE
SET price_per_unit = EXCLUDED.price_per_unit,
    unit = EXCLUDED.unit;

WITH rs AS (
  SELECT id FROM travel.legislation_rate_set WHERE code = 'CZ-2026'
)
INSERT INTO travel.km_compensation_rate(rate_set_id, vehicle_kind, amount_per_km)
SELECT id, 'passenger_car', 5.90 FROM rs
ON CONFLICT (rate_set_id, vehicle_kind) DO UPDATE
SET amount_per_km = EXCLUDED.amount_per_km;
