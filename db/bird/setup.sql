-- Read-only role for the BIRD eval database (bird_eval), run after the data load.
-- Same idea as db/init/30-ro-user.sql: least privilege, limits on the role itself.
-- Safe to run again (idempotent).

\getenv ro_password QUERYLENS_BIRD_RO_PASSWORD

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bird_ro') THEN
        CREATE ROLE bird_ro LOGIN CONNECTION LIMIT 20;
    END IF;
END
$$;
ALTER ROLE bird_ro PASSWORD :'ro_password';

ALTER ROLE bird_ro SET default_transaction_read_only = on;
ALTER ROLE bird_ro SET statement_timeout = '30s';  -- some BIRD gold queries are slow
ALTER ROLE bird_ro SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE bird_ro SET temp_file_limit = '1GB';
ALTER ROLE bird_ro SET search_path = public;

REVOKE ALL ON DATABASE bird_eval FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

GRANT CONNECT ON DATABASE bird_eval TO bird_ro;
GRANT USAGE ON SCHEMA public TO bird_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO bird_ro;
