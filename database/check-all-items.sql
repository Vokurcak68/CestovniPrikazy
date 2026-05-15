\set ON_ERROR_STOP on

-- Check travel requests
SELECT 'TRAVEL REQUESTS:' as type;
SELECT
  request_no,
  status,
  owner_user_id,
  (SELECT email FROM travel.app_user WHERE id = owner_user_id) as owner_email,
  approver_user_id,
  (SELECT email FROM travel.app_user WHERE id = approver_user_id) as approver_email
FROM travel.travel_request
ORDER BY request_no;

-- Check travel orders
SELECT 'TRAVEL ORDERS:' as type;
SELECT
  order_no,
  status,
  owner_user_id,
  (SELECT email FROM travel.app_user WHERE id = owner_user_id) as owner_email
FROM travel.travel_order
ORDER BY order_no;

-- Check pending approval requests for accountants
SELECT 'PENDING APPROVAL REQUESTS (accounting stage):' as type;
SELECT
  ar.id,
  ar.travel_order_id,
  o.order_no,
  ar.stage,
  ar.status,
  ar.approver_user_id,
  (SELECT email FROM travel.app_user WHERE id = ar.approver_user_id) as approver_email
FROM travel.approval_request ar
JOIN travel.travel_order o ON o.id = ar.travel_order_id
WHERE ar.stage = 'accounting' AND ar.status = 'pending'
ORDER BY o.order_no;
