# syntax=docker/dockerfile:1
# PostgreSQL 18 + pgvector, with the Pagila demo database loaded on first start.
FROM pgvector/pgvector:0.8.6-pg18

# Pagila v4.1.1 (https://github.com/devrimgunduz/pagila), pinned by tag and SHA-256,
# so every build gets exactly the same data (and the 13 MB file stays out of git).
# The postgres entrypoint runs /docker-entrypoint-initdb.d/* once, in name order,
# when the data volume is empty.
ADD --chmod=644 \
    --checksum=sha256:071ee940a73c8f4fad2997185788065291607e2c55559e3747959e8275391536 \
    https://raw.githubusercontent.com/devrimgunduz/pagila/pagila-v4.1.1/pagila-schema.sql \
    /docker-entrypoint-initdb.d/10-pagila-schema.sql
ADD --chmod=644 \
    --checksum=sha256:a88efa94c7ae8bc9cf55def4efc9f164d064d5b9cd93f11719ba3b5ace1602f7 \
    https://raw.githubusercontent.com/devrimgunduz/pagila/pagila-v4.1.1/pagila-data.sql \
    /docker-entrypoint-initdb.d/20-pagila-data.sql

# Our own setup, after the data: the read-only role that runs generated SQL.
COPY --chmod=644 init/ /docker-entrypoint-initdb.d/
