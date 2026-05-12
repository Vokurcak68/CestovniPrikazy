\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS travel.vehicle_document (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  vehicle_id uuid NOT NULL REFERENCES travel.vehicle(id) ON DELETE CASCADE,
  client_document_id text,
  document_kind text NOT NULL DEFAULT 'otp',
  file_name text NOT NULL,
  content_type text,
  byte_size bigint NOT NULL DEFAULT 0,
  storage_key text NOT NULL,
  sha256 text NOT NULL,
  uploaded_by uuid REFERENCES travel.app_user(id),
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  CHECK (document_kind IN ('otp', 'other'))
);

CREATE INDEX IF NOT EXISTS ix_vehicle_document_vehicle
ON travel.vehicle_document(vehicle_id, uploaded_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS ux_vehicle_document_client
ON travel.vehicle_document(vehicle_id, client_document_id)
WHERE client_document_id IS NOT NULL;

COMMENT ON TABLE travel.vehicle_document IS 'Přílohy ke kartě vozidla, typicky ofocené OTP / malý technický průkaz.';
