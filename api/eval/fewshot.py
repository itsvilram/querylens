"""Few-shot examples for the eval: hand-written, on Pagila only.

They must never come from BIRD mini-dev (that would leak answers into the
prompt). Pagila is not in the eval set, so these examples teach the answer
format and habits (joins, date ranges, using a hint) without giving anything away.
"""

from app.llm.prompts import Example

PAGILA_EXAMPLES = [
    Example(
        question="How many rentals did each store make in March 2024?",
        sql=(
            "SELECT i.store_id, count(*) AS rentals FROM rental r"
            " JOIN inventory i ON i.inventory_id = r.inventory_id"
            " WHERE r.rental_date >= '2024-03-01' AND r.rental_date < '2024-04-01'"
            " GROUP BY i.store_id ORDER BY i.store_id"
        ),
    ),
    Example(
        question="Which actor appears in the most films? Give the full name.",
        sql=(
            "SELECT a.first_name || ' ' || a.last_name AS actor FROM actor a"
            " JOIN film_actor fa ON fa.actor_id = a.actor_id"
            " GROUP BY a.actor_id ORDER BY count(*) DESC LIMIT 1"
        ),
    ),
    Example(
        question=(
            "What percentage of films are rated R?"
            " Hint: percentage = films rated R / all films * 100"
        ),
        sql="SELECT 100.0 * count(*) FILTER (WHERE rating = 'R') / count(*) FROM film",
    ),
]
