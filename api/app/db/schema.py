"""Describe the allowed tables for the prompt, read from the database itself.

We read pg_catalog, not information_schema: information_schema hides foreign keys
from roles that don't own the tables, and ro_user owns nothing. These are our own
fixed queries, not generated SQL, so the validator's function rules don't apply.

Names are written exactly as SQL needs them: Postgres' own quote_ident() adds
double quotes only when a name has spaces, capitals, symbols or is a reserved
word (e.g. "Free Meal Count (K-12)", "order"). Printed raw, `first date` would
look like a column `first` of type `date`.

Output, one line per table (compact, to save prompt tokens):
    film(film_id integer PK, title text, language_id smallint -> language.language_id, ...)
"""

from __future__ import annotations

import hashlib

import asyncpg

_COLUMNS = """
SELECT c.relname AS table_name,
       quote_ident(c.relname) AS table_sql,
       a.attname AS column_name,
       quote_ident(a.attname) AS column_sql,
       format_type(a.atttypid, a.atttypmod) AS data_type,
       EXISTS (
           SELECT 1 FROM pg_constraint k
           WHERE k.conrelid = c.oid AND k.contype = 'p' AND a.attnum = ANY (k.conkey)
       ) AS is_primary_key
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = ANY ($1::text[])
  AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""

# Partitioned tables (Pagila's payment) keep their foreign keys on each partition
# (payment_p2022_01, ...), not on the parent. pg_partition_root() credits them to
# the parent, and DISTINCT folds the 55 identical copies into one.
_FOREIGN_KEYS = """
SELECT DISTINCT src.relname AS table_name, a.attname AS column_name, dst.relname AS ref_table,
       quote_ident(dst.relname) || '.' || quote_ident(fa.attname) AS reference_sql
FROM pg_constraint k
JOIN pg_class src ON src.oid = coalesce(pg_partition_root(k.conrelid), k.conrelid)
JOIN pg_class dst ON dst.oid = coalesce(pg_partition_root(k.confrelid), k.confrelid)
JOIN pg_namespace n ON n.oid = src.relnamespace
CROSS JOIN LATERAL unnest(k.conkey, k.confkey) AS cols (src_attnum, dst_attnum)
JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = cols.src_attnum
JOIN pg_attribute fa ON fa.attrelid = k.confrelid AND fa.attnum = cols.dst_attnum
WHERE k.contype = 'f' AND n.nspname = 'public' AND src.relname = ANY ($1::text[])
"""


async def describe_schema(pool: asyncpg.Pool[asyncpg.Record], tables: frozenset[str]) -> str:
    names = sorted(t.removeprefix("public.") for t in tables)
    async with pool.acquire() as conn:
        columns = await conn.fetch(_COLUMNS, names)
        foreign_keys = await conn.fetch(_FOREIGN_KEYS, names)

    references = {(fk["table_name"], fk["column_name"]): fk["reference_sql"] for fk in foreign_keys}
    table_sql = {col["table_name"]: col["table_sql"] for col in columns}
    lines: dict[str, list[str]] = {name: [] for name in names}
    for col in columns:
        text = f"{col['column_sql']} {col['data_type']}"
        if col["is_primary_key"]:
            text += " PK"
        ref = references.get((col["table_name"], col["column_name"]))
        if ref:
            text += f" -> {ref}"
        lines[col["table_name"]].append(text)
    return "\n".join(
        f"{table_sql.get(name, name)}({', '.join(cols)})" for name, cols in lines.items()
    )


async def foreign_key_edges(
    pool: asyncpg.Pool[asyncpg.Record], tables: frozenset[str]
) -> frozenset[tuple[str, str]]:
    """Pairs of tables joined by a foreign key, e.g. ("payment", "rental")."""
    names = sorted(t.removeprefix("public.") for t in tables)
    async with pool.acquire() as conn:
        rows = await conn.fetch(_FOREIGN_KEYS, names)
    return frozenset(
        (row["table_name"], row["ref_table"])
        for row in rows
        if row["ref_table"] in names and row["ref_table"] != row["table_name"]
    )


def schema_version(schema_text: str) -> str:
    """A short fingerprint: when the schema changes, cached answers stop matching."""
    return hashlib.sha256(schema_text.encode()).hexdigest()[:12]
