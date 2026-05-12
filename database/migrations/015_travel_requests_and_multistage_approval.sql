\set ON_ERROR_STOP on

DO $$ BEGIN
  CREATE TYPE travel.request_status AS ENUM ('draft', 'submitted', 'approved', 'rejected', 'cancelled');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE travel.approval_stage AS ENUM ('request', 'accounting', 'manager');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS travel.travel_request (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_no text NOT NULL UNIQUE,
  owner_user_id uuid NOT NULL REFERENCES travel.app_user(id) ON DELETE RESTRICT,
  approver_user_id uuid NOT NULL REFERENCES travel.app_user(id) ON DELETE RESTRICT,
  destination text NOT NULL,
  start_at timestamptz NOT NULL,
  end_at timestamptz NOT NULL,
  purpose text NOT NULL,
  status travel.request_status NOT NULL DEFAULT 'draft',
  submitted_at timestamptz,
  approved_at timestamptz,
  rejected_at timestamptz,
  rejection_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (end_at >= start_at)
);

CREATE INDEX IF NOT EXISTS ix_travel_request_owner_status
ON travel.travel_request(owner_user_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS ix_travel_request_approver_status
ON travel.travel_request(approver_user_id, status, submitted_at DESC);

DROP TRIGGER IF EXISTS trg_travel_request_touch ON travel.travel_request;
CREATE TRIGGER trg_travel_request_touch
BEFORE UPDATE ON travel.travel_request
FOR EACH ROW EXECUTE FUNCTION travel.touch_updated_at();

ALTER TABLE travel.travel_order
  ADD COLUMN IF NOT EXISTS travel_request_id uuid REFERENCES travel.travel_request(id) ON DELETE RESTRICT;

ALTER TABLE travel.travel_order
  ADD COLUMN IF NOT EXISTS final_approver_user_id uuid REFERENCES travel.app_user(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_travel_order_request
ON travel.travel_order(travel_request_id);

ALTER TABLE travel.approval_request
  ADD COLUMN IF NOT EXISTS stage travel.approval_stage NOT NULL DEFAULT 'manager';

ALTER TABLE travel.approval_request
  ADD COLUMN IF NOT EXISTS rejection_reason text;

CREATE INDEX IF NOT EXISTS ix_approval_request_stage_pending
ON travel.approval_request(stage, status, approver_user_id, due_at)
WHERE status = 'pending';

COMMENT ON TABLE travel.travel_request IS 'Zadost o vycestovani pred vytvorenim cestovniho prikazu.';
COMMENT ON COLUMN travel.travel_order.travel_request_id IS 'Vazba na schvalenou zadost, ze ktere byl cestak zalozen.';
COMMENT ON COLUMN travel.travel_order.final_approver_user_id IS 'Finalni schvalovatel po ucetni kontrole.';
COMMENT ON COLUMN travel.approval_request.stage IS 'Faze schvaleni: request/accounting/manager.';
