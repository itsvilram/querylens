-- The app's own tables, kept apart from the demo data.
-- querylens_app owns schema "app" (schema_docs: table/column descriptions with
-- embeddings for retrieval). It never runs LLM-generated SQL, and ro_user
-- (which does) cannot see this schema at all.
-- Safe to run again (idempotent), so it also works on an existing database.

\getenv app_password QUERYLENS_APP_PASSWORD

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'querylens_app') THEN
        CREATE ROLE querylens_app LOGIN CONNECTION LIMIT 20;
    END IF;
END
$$;
ALTER ROLE querylens_app PASSWORD :'app_password';

GRANT CONNECT ON DATABASE pagila TO querylens_app;
GRANT USAGE ON SCHEMA public TO querylens_app;  -- to use the vector type, which lives in public

-- 30-ro-user.sql removed EXECUTE on every function in public from PUBLIC.
-- Give back only pgvector's own functions (distance operators etc.), not Pagila's.
DO $$
DECLARE
    fn regprocedure;
BEGIN
    FOR fn IN
        SELECT p.oid::regprocedure
        FROM pg_proc p
        JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e'
        JOIN pg_extension e ON e.oid = d.refobjid AND e.extname = 'vector'
    LOOP
        EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO querylens_app', fn);
    END LOOP;
END
$$;

CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION querylens_app;

CREATE TABLE IF NOT EXISTS app.schema_docs (
    db_id       text NOT NULL,            -- "pagila" or a BIRD database name
    table_name  text NOT NULL,
    column_name text NOT NULL DEFAULT '', -- '' = the document for the whole table
    doc         text NOT NULL,
    embedding   public.vector(384) NOT NULL,  -- BAAI/bge-small-en-v1.5
    PRIMARY KEY (db_id, table_name, column_name)
);
-- No HNSW index on purpose: a few hundred rows per database are scanned exactly
-- in well under a millisecond, and an approximate index could miss a table.
ALTER TABLE app.schema_docs OWNER TO querylens_app;
