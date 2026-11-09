-- Least-privilege application role.
--
-- The API is read-only over the research data but must still write the four
-- authentication tables: it records sign-in attempts, revokes tokens on
-- logout, updates last_login_at, and audits role changes. Granting it SELECT
-- alone looks safer and silently breaks logout.
--
-- Run this as the database owner AFTER 001-004. Then point the API at
-- terra_api and keep the owner role for migrations and the ETL only.
--
--   CREATE ROLE terra_api LOGIN PASSWORD '<from your secret manager>';
--
-- Verified: the full request surface (login, series, geo, benchmark,
-- provenance, admin user list, logout, token revocation) works under these
-- grants and nothing else.

GRANT CONNECT ON DATABASE terra TO terra_api;
GRANT USAGE ON SCHEMA public TO terra_api;

-- Research data: read only, including tables added by later migrations.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO terra_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO terra_api;

-- Authentication: the minimum writes the auth flow actually performs.
GRANT INSERT, UPDATE ON app_user      TO terra_api;  -- register, last_login_at, role/active
GRANT INSERT         ON login_attempt TO terra_api;  -- throttling record
GRANT INSERT, DELETE ON revoked_token TO terra_api;  -- logout, and purging expired rows
GRANT INSERT         ON role_change   TO terra_api;  -- audit trail

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO terra_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO terra_api;

-- Deliberately NOT granted: DELETE on app_user or role_change (an audit trail
-- the application can erase is not an audit trail), and any write at all on
-- observation, series, source_extract, cleaning_run, municipality,
-- benchmark_* . Those change only through the ETL, under the owner role.
