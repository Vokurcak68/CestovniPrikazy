BEGIN;

ALTER TABLE travel.employee_profile
  ADD COLUMN IF NOT EXISTS cost_center_code text,
  ADD COLUMN IF NOT EXISTS cost_center_name text,
  ADD COLUMN IF NOT EXISTS department_name text,
  ADD COLUMN IF NOT EXISTS default_transport_kind travel.transport_kind NOT NULL DEFAULT 'private_car',
  ADD COLUMN IF NOT EXISTS default_vehicle_id uuid REFERENCES travel.vehicle(id) ON DELETE SET NULL;

ALTER TABLE travel.vehicle
  ADD COLUMN IF NOT EXISTS is_default boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX IF NOT EXISTS ux_vehicle_default_per_owner
ON travel.vehicle(owner_user_id)
WHERE is_default;

COMMENT ON COLUMN travel.employee_profile.cost_center_code IS 'Lokální nebo Helios kód střediska pro předvyplnění cestovního příkazu.';
COMMENT ON COLUMN travel.employee_profile.cost_center_name IS 'Lokální nebo Helios název střediska pro předvyplnění cestovního příkazu.';
COMMENT ON COLUMN travel.employee_profile.department_name IS 'Lokální nebo Helios útvar zaměstnance pro předvyplnění cestovního příkazu.';
COMMENT ON COLUMN travel.employee_profile.default_transport_kind IS 'Výchozí druh dopravy pro nový cestovní příkaz.';
COMMENT ON COLUMN travel.employee_profile.default_vehicle_id IS 'Výchozí vozidlo zaměstnance pro nový cestovní příkaz.';
COMMENT ON COLUMN travel.vehicle.is_default IS 'Určuje výchozí vozidlo uživatele pro předvyplnění cestovního příkazu.';

COMMIT;
