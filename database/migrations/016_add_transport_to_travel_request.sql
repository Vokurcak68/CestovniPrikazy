-- Migration: Add transport field to travel_request table
-- Date: 2026-05-12
-- Description: Adds transport kind to travel requests to capture intended mode of transportation

ALTER TABLE travel.travel_request
ADD COLUMN IF NOT EXISTS transport text;

COMMENT ON COLUMN travel.travel_request.transport IS 'Intended mode of transportation (private_car, company_car, public_transport, other)';
