\set ON_ERROR_STOP on

-- Check approval history for CP-2026-0003
SELECT
  ar.id::text as approval_id,
  ar.stage::text,
  ar.status::text,
  ar.step_no,
  ar.requested_at,
  ar.decided_at,
  ar.decision_comment,
  u.email as approver_email
FROM travel.approval_request ar
JOIN travel.travel_order o ON o.id = ar.travel_order_id
LEFT JOIN travel.app_user u ON u.id = ar.approver_user_id
WHERE o.order_no = 'CP-2026-0003'
ORDER BY ar.step_no, ar.requested_at;
