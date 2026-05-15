\set ON_ERROR_STOP on

SELECT
  order_no,
  status,
  travel_request_id,
  owner_user_id,
  (SELECT email FROM travel.app_user WHERE id = owner_user_id) as owner_email
FROM travel.travel_order
WHERE order_no = 'CP-2026-0003';
