"""Join expansion, the fake embedder, description building and gold-table parsing."""

import math
from pathlib import Path

from app.db.schema_docs import MAX_DOC_CHARS, bird_docs, pagila_docs
from app.embed.base import EMBEDDING_DIMS
from app.embed.fake import FakeEmbedder
from app.pipeline.retrieve import connect_tables
from eval.retrieval import gold_tables

# Pagila's foreign keys, simplified:
# payment -> rental -> inventory -> film <- film_category -> category
PAGILA_EDGES = frozenset(
    {
        ("payment", "rental"),
        ("payment", "customer"),
        ("rental", "inventory"),
        ("rental", "customer"),
        ("inventory", "film"),
        ("film_category", "film"),
        ("film_category", "category"),
        ("film_actor", "film"),
        ("film_actor", "actor"),
    }
)

# ---------------------------------------------------------------- join expansion


def test_tables_on_the_join_path_are_added() -> None:
    chosen = connect_tables(["payment", "category"], PAGILA_EDGES)

    assert chosen[:2] == ["payment", "category"][:1] + chosen[1:2]  # best table stays first
    assert set(chosen) == {"payment", "rental", "inventory", "film", "film_category", "category"}


def test_directly_joined_tables_add_nothing() -> None:
    assert connect_tables(["film", "inventory"], PAGILA_EDGES) == ["film", "inventory"]


def test_a_junction_table_joins_two_found_tables() -> None:
    assert set(connect_tables(["actor", "film"], PAGILA_EDGES)) == {"actor", "film_actor", "film"}


def test_tables_too_far_apart_are_kept_but_not_linked() -> None:
    chosen = connect_tables(["payment", "category"], PAGILA_EDGES, max_hops=2)

    assert chosen == ["payment", "category"]  # the 5-join path is longer than max_hops


def test_unknown_table_is_kept() -> None:
    assert connect_tables(["film", "island"], PAGILA_EDGES) == ["film", "island"]


# ---------------------------------------------------------------- fake embedder


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_fake_vectors_have_the_right_size_and_length_one() -> None:
    vector = FakeEmbedder().embed_query("money paid by customers")

    assert len(vector) == EMBEDDING_DIMS
    assert math.isclose(sum(v * v for v in vector), 1.0)


def test_texts_sharing_words_are_closer() -> None:
    fake = FakeEmbedder()
    query = fake.embed_query("how much money was paid")
    payment, actor = fake.embed_documents(["money paid by customers", "actors in films"])

    assert _cosine(query, payment) > _cosine(query, actor)


# ---------------------------------------------------------------- descriptions


def test_pagila_has_one_document_per_table_with_the_known_traps() -> None:
    docs = {d.table_name: d.doc for d in pagila_docs()}

    assert len(docs) == 15
    assert "revenue" in docs["payment"]
    assert "Only stores 1 and 2" in docs["inventory"]


def test_bird_documents_come_from_the_description_csvs(tmp_path: Path) -> None:
    db = tmp_path / "shop"
    db.mkdir()
    (db / "Orders.csv").write_text(
        "﻿original_column_name,column_name,column_description,data_format,value_description\n"
        "Total Price,total price,price paid in USD,real,\n"
        ",,,,\n"
        "note,," + "x" * 1000 + ",text,\n",
        encoding="utf-8",
    )

    docs = bird_docs(tmp_path, "shop")

    assert [(d.table_name, d.column_name) for d in docs] == [
        ("orders", ""),
        ("orders", "Total Price"),
        ("orders", "note"),
    ]
    assert docs[0].doc == "Table orders. Columns: Total Price, note"
    assert docs[1].doc == "orders.Total Price: price paid in USD"
    assert len(docs[2].doc) == MAX_DOC_CHARS  # long descriptions are clipped


# ---------------------------------------------------------------- gold tables


def test_gold_tables_ignore_names_from_the_with_clause() -> None:
    sql = (
        "WITH top AS (SELECT customer_id FROM payment) "
        'SELECT c.name FROM "Customer" c JOIN top t ON t.customer_id = c.id'
    )

    assert gold_tables(sql) == {"payment", "customer"}
