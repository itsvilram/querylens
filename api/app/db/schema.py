"""Describe the allowed tables for the prompt, read from the database itself.

We read pg_catalog, not information_schema: information_schema hides foreign keys
from roles that don't own the tables, and ro_user owns nothing. These are our own
fixed queries, not generated SQL, so the validator's function rules don't apply.

Output, one line per table (compact, to save prompt tokens):
    film(film_id integer PK, title text, language_id smallint -> language.language_id, ...)
"""

from __future__ import annotations

import hashlib

import asyncpg

_COLUMNS = """
SELECT c.relname AS table_name,
       a.attname AS column_name,
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

_FOREIGN_KEYS = """
SELECT src.relname AS table_name, a.attname AS column_name,
       dst.relname AS ref_table, fa.attname AS ref_column
FROM pg_constraint k
JOIN pg_class src ON src.oid = k.conrelid
JOIN pg_class dst ON dst.oid = k.confrelid
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

    references = {
        (fk["table_name"], fk["column_name"]): f"{fk['ref_table']}.{fk['ref_column']}"
        for fk in foreign_keys
    }
    lines: dict[str, list[str]] = {name: [] for name in names}
    for col in columns:
        text = f"{col['column_name']} {col['data_type']}"
        if col["is_primary_key"]:
            text += " PK"
        ref = references.get((col["table_name"], col["column_name"]))
        if ref:
            text += f" -> {ref}"
        lines[col["table_name"]].append(text)
    return "\n".join(f"{name}({', '.join(cols)})" for name, cols in lines.items())


def schema_version(schema_text: str) -> str:
    """A short fingerprint: when the schema changes, cached answers stop matching."""
    return hashlib.sha256(schema_text.encode()).hexdigest()[:12]
