-- Migration: Add travel requests to approver dashboard
-- Date: 2026-05-12
-- Description: Updates approver dashboard views to include pending travel requests alongside travel orders

\set ON_ERROR_STOP on

-- Drop existing views (since we're changing the schema - adding new columns)
DROP VIEW IF EXISTS travel.v_approver_dashboard CASCADE;
DROP VIEW IF EXISTS travel.v_approver_pending_orders CASCADE;

-- Create new v_approver_pending_orders to include both travel orders and travel requests
CREATE VIEW travel.v_approver_pending_orders AS
-- Pending travel orders (from approval_request)
SELECT
  ar.approver_user_id,
  ar.id AS approval_request_id,
  ar.travel_order_id,
  NULL::uuid AS travel_request_id,
  'order'::text AS item_type,
  o.order_no AS item_no,
  o.status::text AS item_status,
  o.purpose,
  o.destination,
  requester.display_name AS requester_name,
  totals.gross_amount,
  totals.balance_rounded,
  ar.requested_at,
  ar.due_at,
  (ar.due_at IS NOT NULL AND ar.due_at < now()) AS is_overdue
FROM travel.approval_request ar
JOIN travel.travel_order o ON o.id = ar.travel_order_id
JOIN travel.app_user requester ON requester.id = o.owner_user_id
LEFT JOIN travel.travel_order_total totals ON totals.travel_order_id = o.id
WHERE ar.status = 'pending'
  AND o.owner_user_id <> ar.approver_user_id

UNION ALL

-- Pending travel requests (submitted, waiting for approval)
SELECT
  tr.approver_user_id,
  NULL::uuid AS approval_request_id,
  NULL::uuid AS travel_order_id,
  tr.id AS travel_request_id,
  'request'::text AS item_type,
  tr.request_no AS item_no,
  tr.status::text AS item_status,
  tr.purpose,
  tr.destination,
  requester.display_name AS requester_name,
  NULL::numeric AS gross_amount,
  NULL::numeric AS balance_rounded,
  tr.submitted_at AS requested_at,
  tr.submitted_at + interval '3 days' AS due_at,  -- Default 3 days for request approval
  (tr.submitted_at + interval '3 days' < now()) AS is_overdue
FROM travel.travel_request tr
JOIN travel.app_user requester ON requester.id = tr.owner_user_id
WHERE tr.status = 'submitted'
  AND tr.owner_user_id <> tr.approver_user_id;

-- v_approver_dashboard already aggregates from v_approver_pending_orders, so it automatically includes requests now
CREATE VIEW travel.v_approver_dashboard AS
SELECT
  approver_user_id,
  count(*) AS pending_count,
  count(*) FILTER (WHERE is_overdue) AS overdue_count,
  min(requested_at) AS oldest_requested_at,
  min(due_at) FILTER (WHERE due_at IS NOT NULL) AS nearest_due_at,
  COALESCE(sum(gross_amount), 0) AS pending_gross_amount
FROM travel.v_approver_pending_orders
GROUP BY approver_user_id;

COMMENT ON VIEW travel.v_approver_pending_orders IS 'Shows pending approvals for both travel orders and travel requests';
COMMENT ON VIEW travel.v_approver_dashboard IS 'Dashboard summary for approvers, includes both orders and requests';
