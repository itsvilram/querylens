"""Plain-English descriptions of tables and columns, used for retrieval (RAG).

One document per table, plus (for BIRD) one per column: a single table document
for a 70-column table would be cut off at the embedding model's 512-token limit,
while column documents let "free meal count" find the right table directly.

Pagila descriptions are hand-written (including traps the tests found). BIRD
descriptions come from its own database_description CSV files. Neither is
written by an LLM: no extra calls, and no chance of injected instructions.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

MAX_DOC_CHARS = 600


@dataclass(frozen=True)
class SchemaDoc:
    db_id: str
    table_name: str
    column_name: str  # "" for the table's own document
    doc: str


PAGILA_TABLES = {
    "actor": "Actors who appear in films: first_name, last_name.",
    "address": "Street addresses of customers, staff and stores; links to city.",
    "category": "Film genres, such as Action, Comedy, Documentary, Sci-Fi (16 in total).",
    "city": "City names; each city belongs to a country.",
    "country": "Country names.",
    "customer": (
        "People who rent films: first_name, last_name, email, active flag, create_date,"
        " their home store_id and address."
    ),
    "film": (
        "The film catalogue: title, description, release_year, rating (G, PG, PG-13, R,"
        " NC-17), length in minutes, rental_rate (price to rent), rental_duration in days,"
        " replacement_cost, language."
    ),
    "film_actor": "Which actors appear in which films (joins film and actor).",
    "film_category": "The genre of each film (joins film and category).",
    "inventory": (
        "Physical copies of films held by stores. Only stores 1 and 2 hold inventory, so"
        " every rental and every film in stock comes from those two stores."
    ),
    "language": "Languages that films are in.",
    "payment": (
        "Money paid by customers for rentals: amount, payment_date, customer_id,"
        " rental_id, staff_id. Use it for revenue, sales, income or how much was spent."
    ),
    "rental": (
        "Each time a customer rented a film copy: rental_date, return_date, inventory_id,"
        " customer_id, staff_id. Use it to count rentals."
    ),
    "staff": "Employees (1,500 rows), each working at a store_id.",
    "store": (
        "Stores (500 rows, ids 0 to 499) with a manager and an address. Only stores 1 and"
        " 2 have inventory and rentals."
    ),
}


def pagila_docs() -> list[SchemaDoc]:
    return [
        SchemaDoc("pagila", table, "", f"Table {table}: {text}")
        for table, text in sorted(PAGILA_TABLES.items())
    ]


def bird_docs(descriptions_dir: Path, db_id: str) -> list[SchemaDoc]:
    """Docs for one BIRD database, from data/bird/descriptions/<db_id>/<table>.csv."""
    docs: list[SchemaDoc] = []
    for csv_path in sorted((descriptions_dir / db_id).glob("*.csv")):
        table = csv_path.stem.lower()  # the Postgres dump lower-cases table names
        columns = _read_columns(csv_path)
        names = ", ".join(name for name, _ in columns)
        docs.append(SchemaDoc(db_id, table, "", _clip(f"Table {table}. Columns: {names}")))
        for name, description in columns:
            text = f"{table}.{name}: {description}" if description else f"{table}.{name}"
            docs.append(SchemaDoc(db_id, table, name, _clip(text)))
    return docs


def _read_columns(csv_path: Path) -> list[tuple[str, str]]:
    # Some BIRD files have a byte-order mark or odd characters: read leniently.
    with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        rows = list(csv.DictReader(handle))
    columns = []
    for row in rows:
        name = (row.get("original_column_name") or "").strip()
        if not name:
            continue
        parts = [row.get("column_description"), row.get("value_description")]
        description = ". ".join(p.strip() for p in parts if p and p.strip())
        columns.append((name, description))
    return columns


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_DOC_CHARS else text[: MAX_DOC_CHARS - 3] + "..."
