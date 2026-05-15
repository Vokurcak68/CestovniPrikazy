-- Kontrola stavu cestovního příkazu CP-2026-0003 v PostgreSQL
SELECT
    order_no AS "Číslo příkazu",
    status AS "Status",
    export_status AS "Export status",
    helios_document_id AS "Helios ID",
    helios_exported_at AS "Exportováno",
    approved_at AS "Schváleno"
FROM travel.travel_order
WHERE order_no = 'CP-2026-0003';
