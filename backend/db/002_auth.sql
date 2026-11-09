-- Authentication and roles.
--
-- Passwords are never stored. Only a scrypt hash with a per-user random salt
-- is kept, and the parameters are stored beside it so they can be raised later
-- without invalidating existing accounts.

CREATE TABLE IF NOT EXISTS app_user (
    user_id       BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    password_hash TEXT NOT NULL,          -- scrypt$n$r$p$salt_b64$hash_b64
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

-- Email is matched case-insensitively; store it lowercased and enforce that here.
CREATE UNIQUE INDEX IF NOT EXISTS app_user_email_lower ON app_user (lower(email));

-- Real logout. A JWT is otherwise valid until it expires, so signing out would
-- be a client-side fiction; revoked token IDs are checked on every request.
CREATE TABLE IF NOT EXISTS revoked_token (
    jti        TEXT PRIMARY KEY,
    user_id    BIGINT REFERENCES app_user(user_id) ON DELETE CASCADE,
    revoked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL        -- rows past this are safe to purge
);

CREATE INDEX IF NOT EXISTS revoked_token_expiry ON revoked_token (expires_at);

-- Failed sign-in attempts, for throttling. Keyed by email and source address so
-- one attacker cannot lock every account by guessing against it.
CREATE TABLE IF NOT EXISTS login_attempt (
    attempt_id  BIGSERIAL PRIMARY KEY,
    email       TEXT NOT NULL,
    source_ip   TEXT,
    succeeded   BOOLEAN NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS login_attempt_recent ON login_attempt (email, attempted_at DESC);

-- Who changed whose role, and when. Role changes are the privileged action in
-- this system, so they are audited rather than merely permitted.
CREATE TABLE IF NOT EXISTS role_change (
    change_id   BIGSERIAL PRIMARY KEY,
    target_user BIGINT NOT NULL REFERENCES app_user(user_id) ON DELETE CASCADE,
    actor_user  BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
    old_role    TEXT NOT NULL,
    new_role    TEXT NOT NULL,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
