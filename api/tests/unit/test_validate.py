"""SQL validator rules, one small case each. Pure functions: no database needed."""

import pytest

from app.db.allowlist import PAGILA_TABLES
from app.pipeline.validate import (
    MAX_SQL_CHARS,
    RejectCode,
    SqlPolicy,
    SqlRejected,
    ValidatedSql,
    validate_sql,
)

POLICY = SqlPolicy(allowed_tables=PAGILA_TABLES, row_cap=100)


def check(sql: str) -> ValidatedSql:
    return validate_sql(sql, POLICY)


def rejection(sql: str) -> SqlRejected:
    with pytest.raises(SqlRejected) as caught:
        check(sql)
    return caught.value


# ---------------------------------------------------------------- allowed

ALLOWED = [
    "SELECT 1",
    "SELECT title FROM film",
    "SELECT title FROM public.film",
    'SELECT "title" FROM "film"',
    "SELECT f.title, c.name FROM film f"
    " JOIN film_category fc ON fc.film_id = f.film_id"
    " JOIN category c ON c.category_id = fc.category_id",
    "SELECT rating, count(*) FROM film GROUP BY rating HAVING count(*) > 10 ORDER BY 2 DESC",
    "WITH top AS (SELECT customer_id, sum(amount) AS total FROM payment GROUP BY customer_id)"
    " SELECT * FROM top ORDER BY total DESC",
    "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 5) SELECT i FROM n",
    "SELECT title FROM film UNION SELECT name FROM category",
    "SELECT title FROM film WHERE film_id IN (SELECT film_id FROM inventory WHERE store_id = 2)",
    "SELECT date_trunc('month', payment_date) AS month, sum(amount) FROM payment"
    " WHERE payment_date >= '2024-01-01' GROUP BY 1",
    "SELECT customer_id, rank() OVER (ORDER BY sum(amount) DESC) FROM payment GROUP BY customer_id",
    "SELECT extract(year FROM rental_date) AS y, count(*) FROM rental GROUP BY y",
    "SELECT coalesce(original_language_id, language_id) FROM film",
    "SELECT d::date FROM generate_series("
    "'2024-01-01'::date, '2024-12-01'::date, interval '1 month') AS d",
    "SELECT 'ignore all instructions; DROP TABLE film' AS just_text",
    "SELECT title FROM film -- DROP TABLE film",
    "SELECT amount FROM payment WHERE amount > 5 FETCH FIRST 10 ROWS ONLY",
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_read_only_queries_are_allowed(sql: str) -> None:
    result = check(sql)

    assert result.sql.upper().startswith(("SELECT", "WITH"))


# ---------------------------------------------------------------- rejected

REJECTED: list[tuple[str, RejectCode]] = [
    # empty, broken, or more than one statement
    ("", "empty"),
    ("   ;  ", "empty"),
    ("SELECT (1", "parse_error"),
    ("SELECT 1; SELECT 2", "multiple_statements"),
    ("SELECT * FROM film; DROP TABLE film", "multiple_statements"),
    # anything that is not a SELECT at the top
    ("INSERT INTO category (name) VALUES ('x')", "not_a_select"),
    ("UPDATE film SET title = 'x'", "not_a_select"),
    ("DELETE FROM rental", "not_a_select"),
    (
        "MERGE INTO film f USING film g ON f.film_id = g.film_id WHEN MATCHED THEN DELETE",
        "not_a_select",
    ),
    ("DROP TABLE film", "not_a_select"),
    ("CREATE TABLE evil (id int)", "not_a_select"),
    ("ALTER TABLE film ADD COLUMN x int", "not_a_select"),
    ("TRUNCATE film", "not_a_select"),
    ("GRANT ALL ON film TO PUBLIC", "not_a_select"),
    ("COPY film TO STDOUT", "not_a_select"),
    ("SET statement_timeout = 0", "not_a_select"),
    ("EXPLAIN ANALYZE DELETE FROM film", "not_a_select"),
    ("CALL do_something()", "not_a_select"),
    ("VACUUM film", "not_a_select"),
    ("BEGIN", "not_a_select"),
    # writes hidden inside a SELECT
    ("WITH gone AS (DELETE FROM rental RETURNING *) SELECT count(*) FROM gone", "writes_data"),
    (
        "WITH x AS (INSERT INTO category (name) VALUES ('x') RETURNING *) SELECT * FROM x",
        "writes_data",
    ),
    ("WITH x AS (UPDATE film SET rental_rate = 0 RETURNING *) SELECT * FROM x", "writes_data"),
    ("SELECT * INTO film_copy FROM film", "select_into"),
    ("SELECT * FROM film FOR UPDATE", "row_locking"),
    ("SELECT * FROM rental FOR SHARE", "row_locking"),
    # tables outside the allow-list
    ("SELECT * FROM pagila.public.film", "cross_database"),
    ("SELECT * FROM pg_catalog.pg_user", "table_not_allowed"),
    ("SELECT * FROM pg_user", "table_not_allowed"),
    ("SELECT * FROM pg_shadow", "table_not_allowed"),
    ("SELECT * FROM information_schema.tables", "table_not_allowed"),
    ("SELECT * FROM film_embedding", "table_not_allowed"),
    ("SELECT * FROM sales_by_store", "table_not_allowed"),
    ("SELECT * FROM payment_p2024_01", "table_not_allowed"),
    ('SELECT * FROM "Film"', "table_not_allowed"),
    ("SELECT * FROM other_schema.film", "table_not_allowed"),
    ("SELECT title FROM film WHERE film_id IN (SELECT usesysid FROM pg_user)", "table_not_allowed"),
    ("WITH film AS (SELECT * FROM pg_user) SELECT * FROM film", "table_not_allowed"),
    # dangerous functions
    ("SELECT pg_sleep(10)", "function_not_allowed"),
    ("SELECT pg_catalog.pg_sleep(10)", "function_not_allowed"),
    ('SELECT "pg_sleep"(10)', "function_not_allowed"),
    ("SELECT title FROM film WHERE pg_sleep(1) IS NOT NULL", "function_not_allowed"),
    ("SELECT * FROM film, LATERAL pg_sleep(10)", "function_not_allowed"),
    ("SELECT pg_read_file('/etc/passwd')", "function_not_allowed"),
    ("SELECT pg_ls_dir('.')", "function_not_allowed"),
    ("SELECT pg_terminate_backend(123)", "function_not_allowed"),
    ("SELECT pg_advisory_lock(1)", "function_not_allowed"),
    ("SELECT lo_import('/etc/passwd')", "function_not_allowed"),
    ("SELECT dblink('host=evil', 'SELECT 1')", "function_not_allowed"),
    ("SELECT query_to_xml('DELETE FROM rental', true, true, '')", "function_not_allowed"),
    ("SELECT table_to_xml_and_xmlschema('film', true, true, '')", "function_not_allowed"),
    ("SELECT set_config('statement_timeout', '0', false)", "function_not_allowed"),
    ("SELECT current_setting('data_directory')", "function_not_allowed"),
    ("SELECT nextval('film_film_id_seq')", "function_not_allowed"),
    ("SELECT txid_current()", "function_not_allowed"),
]


@pytest.mark.parametrize(("sql", "code"), REJECTED)
def test_unsafe_sql_is_rejected_with_the_right_reason(sql: str, code: RejectCode) -> None:
    assert rejection(sql).code == code


def test_too_long_sql_is_rejected_before_parsing() -> None:
    sql = "SELECT 1 " + " " * MAX_SQL_CHARS

    assert rejection(sql).code == "too_long"


def test_parse_error_detail_is_plain_text() -> None:
    detail = rejection("SELECT (1").detail

    assert detail.startswith("The SQL could not be parsed")
    assert "\x1b" not in detail  # no terminal colour codes sent to the LLM


# ---------------------------------------------------------------- row cap (cap = 100)


@pytest.mark.parametrize(
    ("sql", "expected_end"),
    [
        ("SELECT title FROM film", "LIMIT 101"),
        ("SELECT title FROM film LIMIT 10", "LIMIT 10"),
        ("SELECT title FROM film LIMIT 100", "LIMIT 100"),
        ("SELECT title FROM film LIMIT 5000", "LIMIT 101"),
        ("SELECT title FROM film LIMIT ALL", "LIMIT 101"),
        ("SELECT title FROM film LIMIT (SELECT 1000000)", "LIMIT 101"),
        ("SELECT title FROM film FETCH FIRST 10 ROWS ONLY", "FETCH FIRST 10 ROWS ONLY"),
        ("SELECT title FROM film FETCH FIRST 500 ROWS ONLY", "LIMIT 101"),
        ("SELECT title FROM film UNION SELECT name FROM category", "LIMIT 101"),
        ("SELECT * FROM (SELECT title FROM film LIMIT 5000) AS t", "LIMIT 101"),
    ],
)
def test_limit_is_added_or_clamped(sql: str, expected_end: str) -> None:
    assert check(sql).sql.endswith(expected_end)


def test_offset_is_kept_when_limit_is_clamped() -> None:
    result = check("SELECT title FROM film ORDER BY title LIMIT 5000 OFFSET 20")

    assert "LIMIT 101" in result.sql
    assert "OFFSET 20" in result.sql


def test_row_cap_is_passed_to_the_executor() -> None:
    assert check("SELECT 1").row_cap == 100


# ---------------------------------------------------------------- what we run


def test_comments_are_not_in_the_sql_we_run() -> None:
    result = check("SELECT title FROM film /* DROP TABLE film */ -- DELETE FROM rental")

    assert "DROP" not in result.sql
    assert "DELETE" not in result.sql


def test_tables_read_are_reported_with_their_schema() -> None:
    result = check(
        "WITH fc AS (SELECT film_id FROM film_category)"
        " SELECT f.title FROM film f JOIN fc ON fc.film_id = f.film_id"
    )

    assert result.tables == {"public.film", "public.film_category"}  # the CTE "fc" is not a table


def test_same_input_gives_same_output() -> None:
    sql = "SELECT rating, count(*) FROM film GROUP BY rating"

    assert check(sql) == check(sql)


def test_pretty_sql_is_the_same_query_laid_out_for_reading() -> None:
    checked = check("select c.name, count(*) from film f join category c on true group by c.name")

    assert "\nFROM film AS f\n" in checked.pretty
    assert checked.pretty.split() == checked.sql.split()  # only whitespace differs
