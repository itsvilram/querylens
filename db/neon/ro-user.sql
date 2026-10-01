-- The read-only role for the hosted demo on Neon (the local version is
-- db/init/30-ro-user.sql). Run it as the database owner, after loading Pagila:
--
--   QUERYLENS_RO_PASSWORD=... psql "$NEON_DIRECT_URL" -v ON_ERROR_STOP=1 -f db/neon/ro-user.sql
--
-- Two differences from the local script:
-- - the database name comes from psql's DBNAME (Neon's database is "neondb");
-- - no temp_file_limit: only a superuser can set it, and Neon gives you none.
--   The other limits, the read-only default and the grants are the same.

\getenv ro_password QUERYLENS_RO_PASSWORD

CREATE ROLE ro_user LOGIN PASSWORD :'ro_password' CONNECTION LIMIT 20;

ALTER ROLE ro_user SET default_transaction_read_only = on;
ALTER ROLE ro_user SET statement_timeout = '5s';
ALTER ROLE ro_user SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE ro_user SET search_path = public;

-- First take away what every role gets by default (PUBLIC) ...
REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;           -- includes TEMP: no temp tables
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

-- ... then give ro_user exactly what it needs: the 15 base tables, no views,
-- no payment partitions (querying the parent "payment" table is enough).
GRANT CONNECT ON DATABASE :"DBNAME" TO ro_user;
GRANT USAGE ON SCHEMA public TO ro_user;
GRANT SELECT ON
    actor, address, category, city, country, customer, film, film_actor,
    film_category, inventory, language, payment, rental, staff, store
TO ro_user;
