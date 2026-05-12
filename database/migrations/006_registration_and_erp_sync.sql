\set ON_ERROR_STOP on

ALTER TABLE travel.app_user
  ADD COLUMN IF NOT EXISTS email_verified_at timestamptz;

UPDATE travel.app_user
SET email_verified_at = COALESCE(email_verified_at, created_at)
WHERE is_active
  AND email IS NOT NULL
  AND email_verified_at IS NULL;

CREATE TABLE IF NOT EXISTS travel.email_verification_token (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES travel.app_user(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  email citext NOT NULL,
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_email_verification_user_active
ON travel.email_verification_token(user_id, expires_at)
WHERE used_at IS NULL;

COMMENT ON TABLE travel.email_verification_token IS 'Jednorázové tokeny pro ověření e-mailu při samoobslužné registraci.';
