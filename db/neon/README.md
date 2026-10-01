# The demo database on Neon

The hosted demo uses a free [Neon](https://neon.tech) Postgres 18 project. It gets the same Pagila
data and the same read-only role as the local Docker database, minus `film_embedding` (not part of
the demo) and `temp_file_limit` (it needs a superuser, which Neon doesn't give).

Run from the repository root, with the local stack up (`docker compose up -d db`). `NEON_DIRECT_URL`
is the owner's connection string from Neon's **Connect** dialog, with connection pooling off:

```sh
# 1. Copy Pagila from the local database (one transaction: all or nothing).
docker compose exec -T db sh -c "pg_dump -U postgres -d pagila -n public -T public.film_embedding \
  --no-owner --no-privileges | sed 's/^CREATE SCHEMA public;$//' > /tmp/pagila_neon.sql"
docker compose exec -T -e NEON_DIRECT_URL db sh -c \
  'psql "$NEON_DIRECT_URL" -q -v ON_ERROR_STOP=1 --single-transaction -f /tmp/pagila_neon.sql'

# 2. Create ro_user with its limits and grants (choose a long random password).
docker compose exec -T -e NEON_DIRECT_URL -e QUERYLENS_RO_PASSWORD db sh -c \
  'psql "$NEON_DIRECT_URL" -q -v ON_ERROR_STOP=1 -f -' < db/neon/ro-user.sql

# 3. Check the role through the pooled connection the app uses: 17 of 19 executor tests
#    pass; the 2 differences are the two above (the table doesn't exist, the limit isn't set).
READONLY_DATABASE_URL="<ro_user, pooled host>" uv --directory api run pytest tests/integration/test_execute.py
```

The app then reads the database through `READONLY_DATABASE_URL` = `ro_user` on the **pooled** host
(serverless functions open many short connections; the pooler shares them).
