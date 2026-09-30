"""Eval scoring, statistics, subset selection and the reply cache. No network, no database."""

import json
from pathlib import Path

import pytest

from app.llm.base import Message
from app.llm.fake import FakeLLM, fake_answer
from eval.cache import CachedLLM, CacheMiss
from eval.dataset import Question, load_bird, stratified_subset
from eval.metrics import (
    execution_match,
    paired_comparison,
    percentile,
    strict_match,
    wilson_interval,
)

# ---------------------------------------------------------------- execution accuracy (BIRD rule)


def test_same_rows_in_any_order_match() -> None:
    assert execution_match([(1, "a"), (2, "b")], [(2, "b"), (1, "a")])


def test_duplicate_rows_do_not_matter() -> None:
    assert execution_match([(1,), (1,), (2,)], [(1,), (2,)])


def test_column_order_matters() -> None:
    assert not execution_match([("a", 1)], [(1, "a")])


def test_different_rows_do_not_match() -> None:
    assert not execution_match([(1,)], [(2,)])
    assert not execution_match([], [(1,)])


def test_strict_match_also_needs_same_order_and_duplicates() -> None:
    assert strict_match([(1,), (2,)], [(1,), (2,)])
    assert not strict_match([(2,), (1,)], [(1,), (2,)])
    assert not strict_match([(1,), (1,)], [(1,)])


# ---------------------------------------------------------------- statistics


def test_wilson_interval_for_60_of_100_is_about_plus_minus_10_points() -> None:
    low, high = wilson_interval(60, 100)

    assert low == pytest.approx(0.502, abs=0.002)
    assert high == pytest.approx(0.691, abs=0.002)


def test_wilson_interval_stays_inside_0_and_1() -> None:
    assert wilson_interval(0, 10)[0] == 0.0
    assert wilson_interval(10, 10)[1] == 1.0
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_paired_comparison_counts_fixed_and_broken() -> None:
    before = [False, False, True, True, False]
    after = [True, True, True, False, False]

    fixed, broken, _ = paired_comparison(before, after)

    assert (fixed, broken) == (2, 1)


def test_paired_comparison_p_value() -> None:
    # 7 fixed vs 2 broken: exact two-sided McNemar p = 2 * P(X <= 2), X ~ Bin(9, 0.5) = 0.1797
    before = [False] * 7 + [True] * 2
    after = [True] * 7 + [False] * 2

    assert paired_comparison(before, after)[2] == pytest.approx(0.1797, abs=0.0001)


def test_no_changes_means_no_evidence_of_difference() -> None:
    assert paired_comparison([True, False], [True, False]) == (0, 0, 1.0)


def test_percentile() -> None:
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([10.0], 95) == 10.0
    assert percentile([], 50) == 0.0


# ---------------------------------------------------------------- loading BIRD


def _bird_entry(question_id: int, question: str = "q") -> dict[str, object]:
    return {
        "question_id": question_id,
        "db_id": "db",
        "question": question,
        "evidence": "",
        "SQL": "SELECT 1",
        "difficulty": "simple",
    }


def test_identical_duplicate_entries_are_kept_once(tmp_path: Path) -> None:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps([_bird_entry(1), _bird_entry(2), _bird_entry(2)]), "utf-8")

    assert [q.question_id for q in load_bird(path)] == [1, 2]


def test_different_questions_with_the_same_id_are_an_error(tmp_path: Path) -> None:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps([_bird_entry(1, "a"), _bird_entry(1, "b")]), "utf-8")

    with pytest.raises(ValueError, match="share id 1"):
        load_bird(path)


# ---------------------------------------------------------------- subset selection


def _questions() -> list[Question]:
    out = []
    for i in range(200):
        db = "a" if i < 150 else "b"
        level = "simple" if i % 2 else "moderate"
        out.append(Question(i, db, f"q{i}", "", "SELECT 1", level))
    return out


def test_subset_has_exactly_n_and_keeps_group_shares() -> None:
    subset = stratified_subset(_questions(), n=40, seed=1)

    assert len(subset) == 40
    assert sum(q.db_id == "a" for q in subset) == 30  # 75% of the questions are from "a"
    assert sum(q.difficulty == "simple" for q in subset) == 20


def test_subset_leftovers_go_to_the_largest_remainders() -> None:
    # n=10: exact shares are 3.75 / 3.75 / 1.25 / 1.25 -> floors 3/3/1/1 = 8, and the
    # 2 leftover places go to the two groups with remainder .75 (both in "a")
    subset = stratified_subset(_questions(), n=10, seed=1)

    assert len(subset) == 10
    assert sum(q.db_id == "a" for q in subset) == 8


def test_changing_one_group_does_not_reshuffle_the_others() -> None:
    questions = _questions()
    before = stratified_subset(questions, n=40, seed=3)
    # drop one question from group ("b", "moderate"): the "a" picks must not change
    after = stratified_subset([q for q in questions if q.question_id != 150], n=40, seed=3)

    assert [q for q in before if q.db_id == "a"] == [q for q in after if q.db_id == "a"]


def test_subset_is_the_same_for_the_same_seed() -> None:
    first = stratified_subset(_questions(), n=20, seed=7)
    again = stratified_subset(_questions(), n=20, seed=7)
    other = stratified_subset(_questions(), n=20, seed=8)

    assert first == again
    assert first != other


# ---------------------------------------------------------------- reply cache

MESSAGES = [Message("system", "rules"), Message("user", "Question: how many films?")]
IDENTITY = {
    "provider": "gemini",
    "model": "m",
    "reasoning_effort": "low",
    "structured_output": True,
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_second_identical_request_comes_from_disk(tmp_path: Path) -> None:
    inner = FakeLLM({"how many films": fake_answer("SELECT 1")})
    llm = CachedLLM(inner, tmp_path, IDENTITY)

    first = await llm.complete(MESSAGES, json_schema={}, schema_name="x")
    second = await llm.complete(MESSAGES, json_schema={}, schema_name="x")

    assert first == second
    assert len(inner.calls) == 1  # only one real call
    assert (llm.hits, llm.misses) == (1, 1)


@pytest.mark.anyio
async def test_different_model_is_a_different_cache_entry(tmp_path: Path) -> None:
    inner = FakeLLM({"how many films": fake_answer("SELECT 1")})
    await CachedLLM(inner, tmp_path, IDENTITY).complete(MESSAGES, json_schema={}, schema_name="x")

    other = CachedLLM(inner, tmp_path, {**IDENTITY, "model": "other"})

    assert not other.is_cached(MESSAGES, {})


@pytest.mark.anyio
async def test_replay_mode_never_calls_the_network(tmp_path: Path) -> None:
    replay = CachedLLM(None, tmp_path, IDENTITY)

    with pytest.raises(CacheMiss):
        await replay.complete(MESSAGES, json_schema={}, schema_name="x")
