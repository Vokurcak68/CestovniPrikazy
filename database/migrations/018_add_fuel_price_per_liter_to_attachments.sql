-- Add fuel_price_per_liter column to travel_attachment table
-- This allows storing the actual fuel price from receipts for accurate calculation

ALTER TABLE travel.travel_attachment
ADD COLUMN IF NOT EXISTS fuel_price_per_liter numeric(10,2) DEFAULT 0 NOT NULL;

COMMENT ON COLUMN travel.travel_attachment.fuel_price_per_liter IS 'Price per liter of fuel from receipt (in CZK), used for calculating fuel compensation instead of decree rates';
