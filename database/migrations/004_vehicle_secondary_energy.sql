BEGIN;

ALTER TABLE travel.vehicle
  ADD COLUMN IF NOT EXISTS secondary_fuel_type travel.fuel_type,
  ADD COLUMN IF NOT EXISTS secondary_consumption_per_100km numeric(10,3) NOT NULL DEFAULT 0;

COMMENT ON COLUMN travel.vehicle.secondary_fuel_type IS 'Volitelná druhá energie vozidla, například elektřina u plug-in hybridu.';
COMMENT ON COLUMN travel.vehicle.secondary_consumption_per_100km IS 'Spotřeba druhé energie na 100 km, například kWh/100 km.';

COMMIT;
