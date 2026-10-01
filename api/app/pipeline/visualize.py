"""Visualize: pick a chart from the result's column types (a pure function).

The model's chart_hint is only a wish. The columns decide what can be drawn:
- one number                                  -> a big-number card
- a date/time column, then a number column    -> line (or bar, if 2-30 rows)
- any other first column, then a number column -> bar, if there are 2-30 rows
- anything else                               -> table only

The hint wins when it is one of the possible charts; otherwise the first
possible one does. The options go to the UI, so its chart switch only offers
charts that make sense for these rows. A table is always possible.
"""

from typing import Literal

type Chart = Literal["line", "bar", "number", "table"]

# Postgres type names (as asyncpg reports them). money is left out: it comes
# back as text like "$1.00".
NUMBER_TYPES = frozenset({"int2", "int4", "int8", "numeric", "float4", "float8"})
TIME_TYPES = frozenset({"date", "timestamp", "timestamptz"})
MAX_BARS = 30  # more bars than this can't be read; the table is better


def chart_options(column_types: list[str], row_count: int) -> list[Chart]:
    """The charts that fit these columns, best first. Always ends with "table"."""
    if row_count == 0:
        return ["table"]
    if row_count == 1 and len(column_types) == 1 and column_types[0] in NUMBER_TYPES:
        return ["number", "table"]
    # A chart needs a label column (the first) and at least one number after it.
    if not any(t in NUMBER_TYPES for t in column_types[1:]):
        return ["table"]
    options: list[Chart] = []
    if column_types[0] in TIME_TYPES and row_count >= 2:
        options.append("line")
    if 2 <= row_count <= MAX_BARS:  # one bar compares nothing; the table says it better
        options.append("bar")
    return [*options, "table"]


def pick_chart(column_types: list[str], row_count: int, hint: Chart) -> tuple[Chart, list[Chart]]:
    options = chart_options(column_types, row_count)
    return (hint if hint in options else options[0]), options
