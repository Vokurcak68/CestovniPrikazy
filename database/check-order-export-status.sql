\set ON_ERROR_STOP on

-- Check order basic info
SELECT
  order_no,
  status,
  export_status,
  helios_document_id
FROM travel.travel_order
WHERE order_no = 'CP-2026-0003';

-- Check if it appears in the export view
SELECT COUNT(*) as count_in_export_view
FROM travel.vok_cp_export_to_helios
WHERE order_no = 'CP-2026-0003';
