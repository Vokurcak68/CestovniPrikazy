-- Approval requests must always be decided by someone other than the traveller.

UPDATE travel.employee_approver_option option
SET is_active = false,
    is_default = false,
    updated_at = now()
FROM travel.employee_profile profile
WHERE option.employee_profile_id = profile.id
  AND profile.user_id IS NOT NULL
  AND option.approver_user_id = profile.user_id
  AND (option.is_active OR option.is_default);

UPDATE travel.employee_profile
SET default_approver_user_id = NULL
WHERE user_id IS NOT NULL
  AND default_approver_user_id = user_id;

UPDATE travel.approval_request request
SET status = 'cancelled',
    decided_at = now(),
    decision_comment = 'Zruseno systemem: vlastni cestovni prikaz nelze schvalit sam sobe.'
FROM travel.travel_order order_row
WHERE order_row.id = request.travel_order_id
  AND order_row.owner_user_id = request.approver_user_id
  AND request.status = 'pending';

UPDATE travel.notification notification
SET status = 'read',
    read_at = COALESCE(notification.read_at, now())
FROM travel.travel_order order_row
JOIN travel.approval_request request
  ON request.travel_order_id = order_row.id
 AND request.approver_user_id = order_row.owner_user_id
WHERE notification.object_type = 'travel_order'
  AND notification.object_id = order_row.id
  AND notification.recipient_user_id = order_row.owner_user_id
  AND notification.type_code = 'approval_requested'
  AND notification.read_at IS NULL;

UPDATE travel.travel_order order_row
SET status = 'draft',
    current_approver_user_id = NULL,
    submitted_at = NULL,
    export_status = 'not_ready'
WHERE order_row.status = 'submitted'
  AND EXISTS (
    SELECT 1
    FROM travel.approval_request request
    WHERE request.travel_order_id = order_row.id
      AND request.approver_user_id = order_row.owner_user_id
      AND request.status = 'cancelled'
      AND request.decision_comment = 'Zruseno systemem: vlastni cestovni prikaz nelze schvalit sam sobe.'
  );

WITH ranked_pending AS (
  SELECT
    request.id,
    row_number() OVER (
      PARTITION BY request.travel_order_id, request.step_no
      ORDER BY
        (request.approver_user_id = order_row.current_approver_user_id) DESC,
        request.requested_at DESC NULLS LAST,
        request.id DESC
    ) AS keep_rank
  FROM travel.approval_request request
  JOIN travel.travel_order order_row ON order_row.id = request.travel_order_id
  WHERE request.status = 'pending'
    AND order_row.owner_user_id <> request.approver_user_id
)
UPDATE travel.approval_request request
SET status = 'cancelled',
    decided_at = now(),
    decision_comment = 'Nahrazeno novym vyberem schvalovatele.'
FROM ranked_pending ranked
WHERE ranked.id = request.id
  AND ranked.keep_rank > 1;

CREATE OR REPLACE VIEW travel.v_approver_pending_orders AS
SELECT
  ar.approver_user_id,
  ar.id AS approval_request_id,
  ar.travel_order_id,
  o.order_no,
  o.status AS order_status,
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
  AND o.owner_user_id <> ar.approver_user_id;

CREATE OR REPLACE VIEW travel.v_approver_dashboard AS
SELECT
  approver_user_id,
  count(*) AS pending_count,
  count(*) FILTER (WHERE is_overdue) AS overdue_count,
  min(requested_at) AS oldest_requested_at,
  min(due_at) FILTER (WHERE due_at IS NOT NULL) AS nearest_due_at,
  COALESCE(sum(gross_amount), 0) AS pending_gross_amount
FROM travel.v_approver_pending_orders
GROUP BY approver_user_id;
