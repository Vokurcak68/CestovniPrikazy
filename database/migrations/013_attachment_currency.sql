ALTER TABLE travel.travel_attachment
  ADD COLUMN IF NOT EXISTS currency_code char(3) NOT NULL DEFAULT 'CZK',
  ADD COLUMN IF NOT EXISTS exchange_rate numeric(14,6) NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS amount_czk numeric(14,2);

UPDATE travel.travel_attachment
SET amount_czk = COALESCE(amount_czk, round(COALESCE(amount, 0) * COALESCE(NULLIF(exchange_rate, 0), 1), 2))
WHERE amount_czk IS NULL;
