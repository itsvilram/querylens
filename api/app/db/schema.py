"""Describe the allowed tables for the prompt, read from the database itself.

We read pg_catalog, not information_schema: information_schema hides foreign keys
from roles that don't own the tables, and ro_user owns nothing. These are our own
fixed queries, not generated SQL, so the validator's function rules don't apply.

Names are written exactly as SQL needs them: Postgres' own quote_ident() adds
double quotes only when a name has spaces, capitals, symbols or is a reserved
word (e.g. "Free Meal Count (K-12)", "order"). Printed raw, `first date` would
look like a column `first` of type `date`.

read_schema() returns the tables as data (for the schema panel in the UI);
describe_schema() prints them for the prompt, one line per table (compact, to
save prompt tokens):
    film(film_id integer PK, title text, language_id smallint -> language.language_id, ...)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

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
       fa.attname AS ref_column,
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


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    sql_name: str  # as SQL needs it: quoted when it has spaces, capitals, ...
    data_type: str  # e.g. "integer", "character varying(45)"
    primary_key: bool
    references: tuple[str, str] | None  # (table, column) of a foreign key, raw names
    references_sql: str | None  # the same, as SQL: "language.language_id"


@dataclass(frozen=True)
class TableInfo:
    name: str
    sql_name: str
    columns: list[ColumnInfo]


async def read_schema(
    pool: asyncpg.Pool[asyncpg.Record], tables: frozenset[str]
) -> list[TableInfo]:
    """The allowed tables, sorted by name, with their columns in table order."""
    names = sorted(t.removeprefix("public.") for t in tables)
    async with pool.acquire() as conn:
        columns = await conn.fetch(_COLUMNS, names)
        foreign_keys = await conn.fetch(_FOREIGN_KEYS, names)

    refs = {(fk["table_name"], fk["column_name"]): fk for fk in foreign_keys}
    table_sql = {col["table_name"]: col["table_sql"] for col in columns}
    by_table: dict[str, list[ColumnInfo]] = {name: [] for name in names}
    for col in columns:
        ref = refs.get((col["table_name"], col["column_name"]))
        by_table[col["table_name"]].append(
            ColumnInfo(
                name=col["column_name"],
                sql_name=col["column_sql"],
                data_type=col["data_type"],
                primary_key=col["is_primary_key"],
                references=(ref["ref_table"], ref["ref_column"]) if ref else None,
                references_sql=ref["reference_sql"] if ref else None,
            )
        )
    return [TableInfo(name, table_sql.get(name, name), cols) for name, cols in by_table.items()]


def format_schema(tables: list[TableInfo]) -> str:
    def column(col: ColumnInfo) -> str:
        text = f"{col.sql_name} {col.data_type}"
        if col.primary_key:
            text += " PK"
        if col.references_sql:
            text += f" -> {col.references_sql}"
        return text

    return "\n".join(
        f"{table.sql_name}({', '.join(column(c) for c in table.columns)})" for table in tables
    )


async def describe_schema(pool: asyncpg.Pool[asyncpg.Record], tables: frozenset[str]) -> str:
    return format_schema(await read_schema(pool, tables))


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
