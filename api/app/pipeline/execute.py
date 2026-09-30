"""Safe executor: run validated SQL as ro_user and return the rows.

Layers, from outside in:
1. The pool connects as ro_user: it can only SELECT the demo tables, and its
   role has read-only mode, a 5 s timeout and a temp-file limit.
2. Every query runs in a READ ONLY transaction.
3. A per-query statement_timeout (SET LOCAL, so it ends with the transaction).
4. We fetch at most row_cap + 1 rows, even if the SQL somehow has no LIMIT.

We use asyncpg directly, not an ORM: we need exact control over the
transaction, the timeout and how many rows we read.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

import asyncpg

from app.pipeline.validate import ValidatedSql

ExecErrorCode = Literal["timeout", "permission_denied", "write_blocked", "db_error"]


class ExecutionError(Exception):
    """The database refused or failed the query.

    `detail` is the Postgres message (e.g. 'column "x" does not exist'): the
    correction step sends it back to the LLM. The API never shows it raw.
    """

    def __init__(self, code: ExecErrorCode, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code: ExecErrorCode = code
        self.detail = detail


@dataclass(frozen=True)
class Column:
    name: str
    type_name: str  # Postgres type, e.g. "int4", "text", "timestamptz"


@dataclass(frozen=True)
class QueryResult:
    columns: list[Column]
    rows: list[tuple[Any, ...]]
    truncated: bool  # True if the query had more rows than row_cap
    elapsed_ms: float


async def run_readonly(
    pool: asyncpg.Pool[asyncpg.Record], query: ValidatedSql, *, timeout_ms: int
) -> QueryResult:
    started = time.perf_counter()
    try:
        async with pool.acquire() as conn, conn.transaction(readonly=True):
            # is_local=true: like SET LOCAL, the setting ends with this transaction.
            await conn.execute(
                "SELECT set_config('statement_timeout', $1, true)", f"{timeout_ms}ms"
            )
            statement = await conn.prepare(query.sql)
            columns = [Column(a.name, a.type.name) for a in statement.get_attributes()]
            cursor = await statement.cursor()
            records = await cursor.fetch(query.row_cap + 1)
    except asyncpg.QueryCanceledError as error:
        raise ExecutionError("timeout", f"The query took longer than {timeout_ms} ms.") from error
    except asyncpg.InsufficientPrivilegeError as error:
        raise ExecutionError("permission_denied", error.args[0]) from error
    except asyncpg.ReadOnlySQLTransactionError as error:
        raise ExecutionError("write_blocked", error.args[0]) from error
    except asyncpg.PostgresError as error:
        raise ExecutionError("db_error", error.args[0]) from error

    return QueryResult(
        columns=columns,
        rows=[tuple(record) for record in records[: query.row_cap]],
        truncated=len(records) > query.row_cap,
        elapsed_ms=(time.perf_counter() - started) * 1000,
    )
