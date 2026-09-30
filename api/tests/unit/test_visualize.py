"""The chart picker: column types decide what can be drawn; the model's hint picks among those."""

import pytest

from app.pipeline.visualize import MAX_BARS, Chart, chart_options, pick_chart


@pytest.mark.parametrize(
    ("types", "rows", "expected"),
    [
        ([], 0, ["table"]),  # the model declined: nothing to draw
        (["text", "numeric"], 0, ["table"]),  # no rows
        (["int8"], 1, ["number", "table"]),  # "How many films are there?"
        (["numeric"], 1, ["number", "table"]),
        (["text"], 1, ["table"]),  # one word is not a number card
        (["int8", "numeric"], 1, ["bar", "table"]),  # two numbers in one row: not a card
        (["text", "numeric"], 16, ["bar", "table"]),  # revenue per category
        (["mpaa_rating", "int8"], 5, ["bar", "table"]),  # an enum is a category too
        (["int4", "numeric"], 2, ["bar", "table"]),  # store_id, revenue
        (["text", "numeric"], MAX_BARS + 1, ["table"]),  # too many bars to read
        (["date", "int8"], 12, ["line", "bar", "table"]),  # rentals per month
        (["timestamptz", "numeric"], 500, ["line", "table"]),
        (["date", "int8"], 1, ["bar", "table"]),  # one point is not a line
        (["text", "text"], 10, ["table"]),  # no numbers
        (["numeric", "text"], 10, ["table"]),  # the number must come after the label
        (["text", "money"], 10, ["table"]),  # money arrives as text ("$1.00")
    ],
)
def test_chart_options_follow_the_columns(
    types: list[str], rows: int, expected: list[Chart]
) -> None:
    assert chart_options(types, rows) == expected


def test_the_hint_wins_when_it_fits() -> None:
    assert pick_chart(["date", "int8"], 12, "bar") == ("bar", ["line", "bar", "table"])
    assert pick_chart(["text", "numeric"], 16, "table") == ("table", ["bar", "table"])


def test_a_hint_that_does_not_fit_is_ignored() -> None:
    assert pick_chart(["text", "numeric"], 16, "line") == ("bar", ["bar", "table"])
    assert pick_chart(["text", "text"], 3, "number") == ("table", ["table"])
