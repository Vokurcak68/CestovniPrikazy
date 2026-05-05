ALTER TABLE travel.travel_route_line
  ADD COLUMN IF NOT EXISTS foreign_country_code text,
  ADD COLUMN IF NOT EXISTS foreign_country_name text,
  ADD COLUMN IF NOT EXISTS foreign_meal_currency char(3),
  ADD COLUMN IF NOT EXISTS foreign_meal_rate numeric(14,2),
  ADD COLUMN IF NOT EXISTS foreign_exchange_rate numeric(14,6),
  ADD COLUMN IF NOT EXISTS foreign_exchange_rate_date date,
  ADD COLUMN IF NOT EXISTS foreign_meal_amount_czk numeric(14,2);

ALTER TABLE travel.travel_attachment
  ADD COLUMN IF NOT EXISTS helios_expense_code_id integer,
  ADD COLUMN IF NOT EXISTS helios_expense_code_label text;

COMMENT ON COLUMN travel.travel_route_line.foreign_country_code IS 'Kód země pro zahraniční úsek dle Helios view hvw_vok_Oresi_CPCestDZ.KodZeme.';
COMMENT ON COLUMN travel.travel_route_line.foreign_meal_currency IS 'Měna zahraničního stravného dle Helios view hvw_vok_Oresi_CPCestDZ.Mena.';
COMMENT ON COLUMN travel.travel_route_line.foreign_exchange_rate IS 'Kurz k měně zahraničního stravného z Helios kurzovního lístku.';
COMMENT ON COLUMN travel.travel_attachment.helios_expense_code_id IS 'ID nákladového kódu pro import do TabICestaNakl.idNaklKod.';
