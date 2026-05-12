\set ON_ERROR_STOP on

ALTER TABLE travel.employee_profile
  ALTER COLUMN personal_number DROP NOT NULL;

UPDATE travel.employee_profile ep
SET personal_number = NULL
FROM travel.app_user u
WHERE ep.user_id = u.id
  AND ep.personal_number = u.login_name::text
  AND u.login_name::text LIKE '%@%';

COMMENT ON COLUMN travel.employee_profile.personal_number IS 'Osobní číslo zaměstnance. Může být prázdné do chvíle, než ho uživatel zadá nebo synchronizuje z ERP.';
