BEGIN;

ALTER TABLE travel.legislation_rate_set
  ADD COLUMN IF NOT EXISTS regulation_no text,
  ADD COLUMN IF NOT EXISTS source_url text,
  ADD COLUMN IF NOT EXISTS published_at date,
  ADD COLUMN IF NOT EXISTS checked_at timestamptz;

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

ALTER TABLE travel.travel_attachment
  ADD COLUMN IF NOT EXISTS client_attachment_id text,
  ADD COLUMN IF NOT EXISTS document_kind text NOT NULL DEFAULT 'receipt',
  ADD COLUMN IF NOT EXISTS expense_kind text NOT NULL DEFAULT 'other',
  ADD COLUMN IF NOT EXISTS description text,
  ADD COLUMN IF NOT EXISTS document_date date,
  ADD COLUMN IF NOT EXISTS amount numeric(14,2);

CREATE UNIQUE INDEX IF NOT EXISTS ux_travel_attachment_client
ON travel.travel_attachment(travel_order_id, client_attachment_id)
WHERE client_attachment_id IS NOT NULL;

UPDATE travel.legislation_rate_set
SET regulation_no = COALESCE(regulation_no, '573/2025 Sb.'),
    source_url = COALESCE(source_url, 'https://ppropo.mpsv.cz/Vyhlaska_573_2025'),
    published_at = COALESCE(published_at, DATE '2025-12-18'),
    checked_at = COALESCE(checked_at, now())
WHERE code = 'CZ-2026';

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

COMMIT;
