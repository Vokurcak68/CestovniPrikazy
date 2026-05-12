CREATE INDEX IF NOT EXISTS ix_travel_order_helios_import_candidates
ON travel.travel_order(status, export_status, approved_at DESC, updated_at DESC)
WHERE helios_document_id IS NULL;

CREATE INDEX IF NOT EXISTS ix_travel_order_helios_document_id
ON travel.travel_order(helios_document_id)
WHERE helios_document_id IS NOT NULL;

COMMENT ON COLUMN travel.travel_order.helios_document_id IS
'ID zalozene hlavicky cestovniho prikazu v Heliosu, typicky dbo.TabICestak.id. Po uspesnem importu se posila z Heliosu pres API callback, pripadne jako project.code.';
