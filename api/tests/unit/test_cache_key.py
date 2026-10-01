"""The answer-cache key: same meaning -> same key; anything that changes the answer -> new key."""

from app.config import Settings
from app.pipeline.cache_key import answer_cache_key, normalize_question, pipeline_fingerprint

SCHEMA = "film(film_id integer PK, title text)"


def fingerprint(schema_text: str = SCHEMA, model: str = "m1", **overrides: object) -> str:
    settings = Settings(**overrides)  # type: ignore[arg-type]
    return pipeline_fingerprint(schema_text=schema_text, model=model, settings=settings)


def test_normalize_ignores_case_spacing_and_final_punctuation() -> None:
    assert normalize_question("  How many   FILMS are there?! ") == "how many films are there"


def test_same_question_typed_differently_shares_a_key() -> None:
    fp = fingerprint()
    assert answer_cache_key("How many films are there?", fp) == answer_cache_key(
        "how many films are there", fp
    )


def test_different_questions_get_different_keys() -> None:
    fp = fingerprint()
    assert answer_cache_key("How many films?", fp) != answer_cache_key("How many actors?", fp)


def test_key_has_a_fixed_shape() -> None:
    key = answer_cache_key("x" * 500, fingerprint())
    assert key.startswith("answer:v3:")
    assert len(key) == len("answer:v3:") + 32


def test_anything_that_changes_the_answer_changes_the_fingerprint() -> None:
    base = fingerprint()
    assert fingerprint(schema_text=SCHEMA + "\nactor(actor_id integer PK)") != base
    assert fingerprint(model="m2") != base
    assert fingerprint(row_cap=10) != base
    assert fingerprint(correction_retries=0) != base
    assert fingerprint(schema_mode="retrieved") != base


def test_retrieval_settings_matter_only_when_retrieval_is_on() -> None:
    assert fingerprint(retrieval_k=8) == fingerprint(retrieval_k=4)
    assert fingerprint(schema_mode="retrieved", retrieval_k=8) != fingerprint(
        schema_mode="retrieved", retrieval_k=4
    )


def test_settings_that_do_not_change_the_answer_keep_the_fingerprint() -> None:
    assert fingerprint(rate_limit_per_minute=1, daily_token_budget=5) == fingerprint()
