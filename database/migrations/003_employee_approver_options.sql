BEGIN;

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

INSERT INTO travel.employee_approver_option(employee_profile_id, approver_user_id, is_default, source_system, is_active)
SELECT ep.id, ep.default_approver_user_id, true, 'local', true
FROM travel.employee_profile ep
WHERE ep.default_approver_user_id IS NOT NULL
ON CONFLICT (employee_profile_id, approver_user_id) DO UPDATE
SET is_default = true,
    is_active = true,
    updated_at = now();

COMMENT ON TABLE travel.employee_approver_option IS 'Seznam povolených schvalovatelů zaměstnance; jeden může být výchozí.';

COMMIT;
