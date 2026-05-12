\set ON_ERROR_STOP on

ALTER TABLE travel.vehicle
  ADD COLUMN IF NOT EXISTS source_system travel.user_source NOT NULL DEFAULT 'local',
  ADD COLUMN IF NOT EXISTS helios_export_status travel.export_status NOT NULL DEFAULT 'not_ready',
  ADD COLUMN IF NOT EXISTS helios_export_requested_at timestamptz,
  ADD COLUMN IF NOT EXISTS helios_exported_at timestamptz,
  ADD COLUMN IF NOT EXISTS helios_export_failed_at timestamptz,
  ADD COLUMN IF NOT EXISTS helios_export_error text,
  ADD COLUMN IF NOT EXISTS helios_export_travel_order_id uuid REFERENCES travel.travel_order(id) ON DELETE SET NULL;

UPDATE travel.vehicle
SET source_system = CASE
      WHEN helios_id IS NOT NULL THEN 'helios'::travel.user_source
      ELSE source_system
    END,
    helios_export_status = CASE
      WHEN helios_id IS NOT NULL THEN 'exported'::travel.export_status
      ELSE helios_export_status
    END,
    helios_exported_at = CASE
      WHEN helios_id IS NOT NULL THEN COALESCE(helios_exported_at, updated_at, created_at, now())
      ELSE helios_exported_at
    END
WHERE helios_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_vehicle_helios_export_status
ON travel.vehicle(helios_export_status, helios_export_requested_at)
WHERE is_active;

COMMENT ON COLUMN travel.vehicle.source_system IS 'Původ vozidla: lokální aplikace, Helios, nebo kombinace po lokální úpravě.';
COMMENT ON COLUMN travel.vehicle.helios_export_status IS 'Stav založení/synchronizace lokálně zadaného vozidla do ERP Helios.';
COMMENT ON COLUMN travel.vehicle.helios_export_travel_order_id IS 'Cestovní příkaz, který vyvolal požadavek na založení vozidla v ERP.';
