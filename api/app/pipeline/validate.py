"""SQL validator: decide whether LLM-written SQL is safe to run, using its syntax tree.

Pure functions only: no database, no network, no clock. The same input always
gives the same answer, which makes every rule easy to test.

We never run the SQL string the LLM wrote. We parse it into a tree, check the
tree, and run the SQL that sqlglot generates back from the checked tree. So
what runs is exactly what was checked, and comments are dropped on the way.

This is one layer of several. The database role, the read-only transaction and
the timeout still protect us if a rule here has a gap.
"""

import re
from dataclasses import dataclass
from typing import Literal

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

MAX_SQL_CHARS = 10_000

RejectCode = Literal[
    "empty",
    "too_long",
    "parse_error",
    "multiple_statements",
    "not_a_select",
    "writes_data",
    "select_into",
    "row_locking",
    "cross_database",
    "table_not_allowed",
    "function_not_allowed",
]


class SqlRejected(Exception):
    """The SQL is not safe to run.

    `code` is for logs and metrics. `detail` is one plain sentence that the
    correction step can send back to the LLM.
    """

    def __init__(self, code: RejectCode, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code: RejectCode = code
        self.detail = detail


@dataclass(frozen=True)
class SqlPolicy:
    allowed_tables: frozenset[str]  # "schema.table", lower case, e.g. "public.film"
    row_cap: int  # the most rows the caller wants back


@dataclass(frozen=True)
class ValidatedSql:
    sql: str  # regenerated from the checked tree, with a LIMIT: run this, nothing else
    row_cap: int
    tables: frozenset[str]  # the tables it reads, e.g. for logs and the UI


# Statement types that write or change the database, wherever they appear.
# (Postgres even allows `WITH d AS (DELETE ... RETURNING *) SELECT ...`.)
_WRITE_NODES = (exp.DML, exp.DDL, exp.Command, exp.Set, exp.TruncateTable)

# Functions generated SQL may never call:
# - pg_*: system functions (sleep, file access, advisory locks, killing sessions, ...)
# - lo_*, loread, lowrite: large objects (server file import/export)
# - dblink*: connections to other databases
# - *_to_xml*: they run a query passed as text, which this validator can't see
# - set_config, current_setting: read or change server settings (like the timeout)
# - sequence functions: nextval/setval write, and no analytics question needs them
_DENIED_FUNCTIONS = frozenset(
    {
        "set_config",
        "current_setting",
        "nextval",
        "setval",
        "currval",
        "lastval",
        "loread",
        "lowrite",
    }
)
_DENIED_PREFIXES = ("pg_", "lo_", "dblink", "txid_")
_DENIED_SUFFIXES = ("_to_xml", "_to_xmlschema", "_to_xml_and_xmlschema")

_ANSI_CODES = re.compile(r"\x1b\[[0-9;]*m")


def validate_sql(sql: str, policy: SqlPolicy) -> ValidatedSql:
    """Return the safe SQL to run, or raise SqlRejected with the reason."""
    tree = _parse_single_statement(sql)
    _check_only_reads(tree)
    tables = _check_tables(tree, policy.allowed_tables)
    _check_functions(tree)
    _apply_row_cap(tree, policy.row_cap)
    return ValidatedSql(
        sql=tree.sql(dialect="postgres", comments=False),
        row_cap=policy.row_cap,
        tables=tables,
    )


def _parse_single_statement(sql: str) -> exp.Expr:
    if not sql.strip():
        raise SqlRejected("empty", "The SQL is empty.")
    if len(sql) > MAX_SQL_CHARS:
        raise SqlRejected("too_long", f"The SQL is longer than {MAX_SQL_CHARS} characters.")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except SqlglotError as error:
        first_line = _ANSI_CODES.sub("", str(error)).splitlines()[0]
        raise SqlRejected("parse_error", f"The SQL could not be parsed: {first_line}") from error
    if not statements:
        raise SqlRejected("empty", "The SQL is empty.")
    if len(statements) > 1:
        raise SqlRejected("multiple_statements", "Send exactly one SQL statement.")
    return statements[0]


def _check_only_reads(tree: exp.Expr) -> None:
    # The top must be a SELECT, or a UNION / INTERSECT / EXCEPT of SELECTs.
    # A WITH clause is part of these nodes, so `WITH ... SELECT` is fine.
    if not isinstance(tree, exp.Select | exp.SetOperation):
        raise SqlRejected("not_a_select", "Only SELECT queries are allowed (WITH is fine).")
    for node in tree.walk():
        if isinstance(node, _WRITE_NODES):
            raise SqlRejected(
                "writes_data", f"{node.key.upper()} is not allowed: the query may only read data."
            )
        if isinstance(node, exp.Into):
            raise SqlRejected("select_into", "SELECT ... INTO creates a table and is not allowed.")
        if isinstance(node, exp.Lock):
            raise SqlRejected("row_locking", "FOR UPDATE / FOR SHARE is not allowed.")


def _check_tables(tree: exp.Expr, allowed: frozenset[str]) -> frozenset[str]:
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    used: set[str] = set()
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            continue  # a table function like generate_series(): _check_functions covers it
        if table.catalog:
            raise SqlRejected(
                "cross_database", f"Use tables of this database only, not {table.sql('postgres')}."
            )
        name = _normalized_name(table.this)
        schema_node = table.args.get("db")
        schema = _normalized_name(schema_node) if schema_node else ""
        if not schema and name in cte_names:
            continue  # a name defined in this query's WITH clause, not a real table
        qualified = f"{schema or 'public'}.{name}"
        if qualified not in allowed:
            raise SqlRejected("table_not_allowed", f"The table {qualified} is not available.")
        used.add(qualified)
    return frozenset(used)


def _normalized_name(identifier: exp.Expr) -> str:
    # Postgres folds unquoted names to lower case; "Quoted" names keep their case.
    quoted = isinstance(identifier, exp.Identifier) and bool(identifier.args.get("quoted"))
    return identifier.name if quoted else identifier.name.lower()


def _check_functions(tree: exp.Expr) -> None:
    for func in tree.find_all(exp.Func):
        name = _function_name(func)
        if (
            name in _DENIED_FUNCTIONS
            or name.startswith(_DENIED_PREFIXES)
            or name.endswith(_DENIED_SUFFIXES)
        ):
            raise SqlRejected("function_not_allowed", f"The function {name}() is not allowed.")


def _function_name(func: exp.Func) -> str:
    # Functions sqlglot doesn't know become Anonymous nodes that keep their name.
    # For known ones, use the name as it appears in the Postgres SQL we will run.
    if isinstance(func, exp.Anonymous):
        return func.name.lower()
    rendered = func.sql(dialect="postgres")
    return rendered.split("(", 1)[0].strip().strip('"').lower()


def _apply_row_cap(tree: exp.Expr, row_cap: int) -> None:
    """Make the query return at most row_cap + 1 rows.

    A LIMIT of row_cap or less is kept. Anything else becomes LIMIT row_cap + 1:
    the extra row is never shown, it only tells the executor the result was cut.
    """
    requested = _requested_rows(tree.args.get("limit"))
    if requested is not None and requested <= row_cap:
        return
    tree.set("limit", exp.Limit(expression=exp.Literal.number(row_cap + 1)))


def _requested_rows(limit: exp.Expr | None) -> int | None:
    """The row count a LIMIT / FETCH FIRST asks for, or None if unknown."""
    if isinstance(limit, exp.Limit):
        count = limit.expression
    elif isinstance(limit, exp.Fetch):
        count = limit.args.get("count")
        if count is None:
            return 1  # FETCH FIRST ROW ONLY
    else:
        return None
    if isinstance(count, exp.Literal) and count.is_int:
        return int(count.this)
    return None  # an expression, e.g. LIMIT (SELECT 10^9): replaced by the cap
