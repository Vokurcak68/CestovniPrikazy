\set ON_ERROR_STOP on

DO $$ BEGIN
  CREATE TYPE travel.route_segment_type AS ENUM ('private', 'domestic', 'foreign');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE travel.travel_route_line
  ADD COLUMN IF NOT EXISTS segment_type travel.route_segment_type NOT NULL DEFAULT 'domestic';

COMMENT ON COLUMN travel.travel_route_line.segment_type IS 'Typ úseku vyúčtování pracovní cesty: soukromý, tuzemský, zahraniční.';
