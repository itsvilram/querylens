-- The read-only role that runs every LLM-generated query.
-- Least privilege: it can read the Pagila tables and nothing else.
-- Its limits live on the role itself, so a session can't skip them
-- (and the SQL validator blocks SET and set_config() as well).

-- Password comes from the container environment (see docker-compose.yml).
\getenv ro_password QUERYLENS_RO_PASSWORD

CREATE ROLE ro_user LOGIN PASSWORD :'ro_password' CONNECTION LIMIT 20;

ALTER ROLE ro_user SET default_transaction_read_only = on;
ALTER ROLE ro_user SET statement_timeout = '5s';
ALTER ROLE ro_user SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE ro_user SET temp_file_limit = '100MB';  -- only a superuser can change this one
ALTER ROLE ro_user SET search_path = public;

-- First take away what every role gets by default (PUBLIC) ...
REVOKE ALL ON DATABASE pagila FROM PUBLIC;           -- includes TEMP: no temp tables
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

-- ... then give ro_user exactly what it needs: the base tables, no views,
-- no payment partitions (querying the parent "payment" table is enough),
-- and not film_embedding (not part of the demo schema).
GRANT CONNECT ON DATABASE pagila TO ro_user;
GRANT USAGE ON SCHEMA public TO ro_user;
GRANT SELECT ON
    actor, address, category, city, country, customer, film, film_actor,
    film_category, inventory, language, payment, rental, staff, store
TO ro_user;
