"""Tables that generated SQL may read in the Pagila demo database.

These are the base tables only: no views, no payment_p* partitions (the parent
`payment` table is enough) and no film_embedding. It must match the GRANTs in
db/init/30-ro-user.sql; an integration test checks that they agree.
"""

PAGILA_TABLES: frozenset[str] = frozenset(
    f"public.{name}"
    for name in (
        "actor",
        "address",
        "category",
        "city",
        "country",
        "customer",
        "film",
        "film_actor",
        "film_category",
        "inventory",
        "language",
        "payment",
        "rental",
        "staff",
        "store",
    )
)
