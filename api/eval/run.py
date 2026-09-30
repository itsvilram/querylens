"""Eval runner: answer each question with the real pipeline code and score it.

Examples (run from api/):
    uv run python -m eval.run --name B0                       # BIRD, 100 questions, full schema
    uv run python -m eval.run --dataset pagila_ci --llm replay # CI: recorded replies, no network

It uses the same modules as the app (prompts, generate, validate, execute), but
not the app's Redis cache, rate limit or budget, and with a high row cap so the
API's LIMIT clamp can't turn a right answer into a wrong one.

Each question's result is appended to eval/results/<name>.jsonl as soon as it
is scored, so a run stopped by the daily limit resumes where it stopped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg

from app.api.serialize import JsonValue, to_json_value
from app.config import PROVIDER_BASE_URLS, Settings
from app.db.allowlist import PAGILA_TABLES
from app.db.schema import describe_schema, foreign_key_edges
from app.embed.base import Embedder
from app.embed.fastembed_impl import FastEmbedder
from app.llm.base import LLMRateLimited, Message, Usage
from app.llm.openai_compat import OpenAICompatibleClient
from app.llm.prompts import build_messages
from app.pipeline.execute import ExecutionError, run_readonly
from app.pipeline.generate import ANSWER_SCHEMA, GenerationError, generate_sql
from app.pipeline.retrieve import connect_tables, search_tables
from app.pipeline.validate import SqlPolicy, SqlRejected, ValidatedSql, validate_sql
from eval.cache import CachedLLM
from eval.dataset import REPO, Question, bird_tables, load_bird_subset, load_pagila_ci
from eval.fewshot import PAGILA_EXAMPLES
from eval.metrics import execution_match, percentile, strict_match, wilson_interval

EVAL_ROW_CAP = 100_000  # high: the API's clamp (1,000) would make right answers look wrong
PRED_TIMEOUT_MS = 30_000
GOLD_TIMEOUT_MS = 60_000
RESULTS_DIR = Path(__file__).parent / "results"
CACHE_DIRS = {
    "bird": REPO / "data" / "eval_cache",  # git-ignored
    "pagila_ci": Path(__file__).parent / "fixtures" / "cache",  # committed, for CI replay
}
REQUESTS_PER_MINUTE = {  # free-tier limits (AI Studio → Rate Limit, 2026-09-30)
    "gemini-3.5-flash-lite": 15,
    "gemini-3.1-flash-lite": 15,
    "gemini-3.8-flash": 5,
}


class StopRun(Exception):
    """The provider keeps saying "too many requests": most likely the daily limit."""


@dataclass
class Record:
    question_id: int
    db_id: str
    difficulty: str
    status: str  # correct | wrong | declined | bad_json | blocked | db_error | timeout
    correct: bool
    strict: bool
    detail: str
    predicted_sql: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    llm_ms: float | None  # None when the reply came from the cache
    db_ms: float | None
    tables_sent: int | None = None  # tables in the prompt (full schema: all of them)


# ---------------------------------------------------------------- helpers


def rows_as_tuples(rows: list[tuple[Any, ...]]) -> list[tuple[JsonValue, ...]]:
    """Normalize values (Decimal → float, dates → ISO text) so both sides compare alike."""
    return [tuple(_hashable(to_json_value(v)) for v in row) for row in rows]


def _hashable(value: JsonValue) -> Any:
    return tuple(_hashable(v) for v in value) if isinstance(value, list) else value


async def gold_rows(pool: asyncpg.Pool[asyncpg.Record], q: Question, cache_dir: Path) -> list[Any]:
    """Run the gold SQL once and keep its rows on disk (gold SQL is trusted: no validator)."""
    path = cache_dir / "gold" / f"{q.db_id}_{q.question_id}.json"
    if path.exists():
        return [tuple(_hashable(v) for v in row) for row in json.loads(path.read_text("utf-8"))]
    result = await run_readonly(
        pool, ValidatedSql(q.gold_sql, EVAL_ROW_CAP, frozenset()), timeout_ms=GOLD_TIMEOUT_MS
    )
    rows = rows_as_tuples(result.rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")
    return rows


class Pacer:
    """Keep network calls under the provider's requests-per-minute limit."""

    def __init__(self, rpm: int) -> None:
        self._gap = 60 / rpm * 1.1  # 10% margin
        self._last = 0.0

    async def wait(self) -> None:
        pause = self._last + self._gap - time.monotonic()
        if pause > 0:
            await asyncio.sleep(pause)
        self._last = time.monotonic()


async def ask_model(llm: CachedLLM, messages: list[Message], pacer: Pacer) -> Any:
    """generate_sql, with pacing for network calls and patience for rate limits."""
    for attempt in range(4):
        if not llm.is_cached(messages, ANSWER_SCHEMA):
            await pacer.wait()
        try:
            return await generate_sql(llm, messages)
        except LLMRateLimited as error:
            if attempt == 3:
                raise StopRun from error
            await asyncio.sleep(error.retry_after_s or 60)
    raise AssertionError("unreachable")


# ---------------------------------------------------------------- one question


async def score(
    q: Question,
    *,
    llm: CachedLLM,
    pacer: Pacer,
    pool: asyncpg.Pool[asyncpg.Record],
    schema_text: str,
    tables_sent: int,
    tables: frozenset[str],
    options: argparse.Namespace,
    cache_dir: Path,
) -> Record:
    messages = build_messages(
        q.question,
        schema_text=schema_text,
        examples=PAGILA_EXAMPLES if options.fewshot else None,
        hint=q.evidence if options.evidence and q.evidence else None,
    )
    was_cached = llm.is_cached(messages, ANSWER_SCHEMA)
    usage = Usage(0, 0, 0)
    llm_ms: float | None = None

    def record(
        status: str,
        detail: str = "",
        sql: str = "",
        strict: bool = False,
        db_ms: float | None = None,
    ) -> Record:
        return Record(
            question_id=q.question_id,
            db_id=q.db_id,
            difficulty=q.difficulty,
            status=status,
            correct=status == "correct",
            strict=strict,
            detail=detail[:300],
            predicted_sql=sql,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            llm_ms=llm_ms,
            db_ms=db_ms,
            tables_sent=tables_sent,
        )

    started = time.perf_counter()
    try:
        generation = await ask_model(llm, messages, pacer)
    except GenerationError as error:
        usage = error.usage
        return record("bad_json", error.detail)
    usage = generation.usage
    llm_ms = None if was_cached else (time.perf_counter() - started) * 1000

    sql = generation.answer.sql
    if not sql.strip():
        return record("declined", generation.answer.explanation)
    try:
        validated = validate_sql(sql, SqlPolicy(tables, row_cap=EVAL_ROW_CAP))
    except SqlRejected as error:
        return record("blocked", f"{error.code}: {error.detail}", sql)
    try:
        result = await run_readonly(pool, validated, timeout_ms=PRED_TIMEOUT_MS)
    except ExecutionError as error:
        status = "timeout" if error.code == "timeout" else "db_error"
        return record(status, error.detail, validated.sql)

    predicted = rows_as_tuples(result.rows)
    gold = await gold_rows(pool, q, cache_dir)
    status = "correct" if execution_match(predicted, gold) else "wrong"
    return record(status, "", validated.sql, strict_match(predicted, gold), result.elapsed_ms)


# ---------------------------------------------------------------- summary


def summarize(records: list[Record], meta: dict[str, Any]) -> dict[str, Any]:
    total = len(records)
    correct = sum(r.correct for r in records)
    low, high = wilson_interval(correct, total)
    by_difficulty = {
        level: {
            "correct": sum(r.correct for r in records if r.difficulty == level),
            "total": sum(1 for r in records if r.difficulty == level),
        }
        for level in ("simple", "moderate", "challenging")
        if any(r.difficulty == level for r in records)
    }
    statuses: dict[str, int] = {}
    for r in records:
        statuses[r.status] = statuses.get(r.status, 0) + 1
    llm_times = [r.llm_ms for r in records if r.llm_ms is not None]
    db_times = [r.db_ms for r in records if r.db_ms is not None]
    return {
        **meta,
        "questions": total,
        "ex": {
            "correct": correct,
            "accuracy": round(correct / total, 4) if total else 0,
            "ci95": [round(low, 4), round(high, 4)],
        },
        "strict_ex": {"correct": sum(r.strict for r in records)},
        "by_difficulty": by_difficulty,
        "by_status": dict(sorted(statuses.items())),
        "tokens": {
            "prompt_mean": round(sum(r.prompt_tokens for r in records) / max(total, 1)),
            "prompt_max": max((r.prompt_tokens for r in records), default=0),
            "total_mean": round(sum(r.total_tokens for r in records) / max(total, 1)),
        },
        "latency_ms": {
            "llm_p50": round(percentile(llm_times, 50)),
            "llm_p95": round(percentile(llm_times, 95)),
            "db_p50": round(percentile(db_times, 50), 1),
            "db_p95": round(percentile(db_times, 95), 1),
            "llm_measured": len(llm_times),
        },
    }


def as_markdown(summary: dict[str, Any]) -> str:
    ex, n = summary["ex"], summary["questions"]
    tokens, latency = summary["tokens"], summary["latency_ms"]
    low, high = ex["ci95"]
    lines = [
        f"# Eval run `{summary['name']}`",
        "",
        f"- Dataset: {summary['dataset']}, {n} questions; model: {summary['model']}",
        f"- Options: {summary['options']}",
        f"- **Execution accuracy: {ex['correct']}/{n} = {ex['accuracy']:.1%}**"
        f" (95% interval {low:.1%} to {high:.1%})",
        f"- Strict (same order): {summary['strict_ex']['correct']}/{n}",
        "",
        "| Difficulty | Correct | Total |",
        "|---|---|---|",
        *(f"| {k} | {v['correct']} | {v['total']} |" for k, v in summary["by_difficulty"].items()),
        "",
        "| Outcome | Count |",
        "|---|---|",
        *(f"| {k} | {v} |" for k, v in summary["by_status"].items()),
        "",
        f"Tokens per question: prompt {tokens['prompt_mean']} (max {tokens['prompt_max']}),"
        f" total {tokens['total_mean']}. LLM latency p50/p95: {latency['llm_p50']}"
        f"/{latency['llm_p95']} ms ({latency['llm_measured']} live calls).",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- main


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--name", help="run name (results file); default: <dataset>_<options>")
    parser.add_argument("--dataset", choices=["bird", "pagila_ci"], default="bird")
    parser.add_argument("--provider", choices=["gemini", "groq"], default="gemini")
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--llm", choices=["real", "replay"], default="real")
    parser.add_argument("--schema", choices=["full", "retrieved"], default="full")
    parser.add_argument("--k", type=int, default=4, help="tables to retrieve (--schema retrieved)")
    parser.add_argument("--fewshot", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--evidence", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--limit", type=int, help="only the first N questions (for a quick try)")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--expect", type=Path, help="fail unless the result matches this summary")
    return parser.parse_args(argv)


async def main(options: argparse.Namespace) -> int:
    settings = Settings()
    bird = options.dataset == "bird"
    questions = load_bird_subset() if bird else load_pagila_ci()
    if options.limit:
        questions = questions[: options.limit]
    tables = bird_tables() if bird else {"pagila": PAGILA_TABLES}
    dsn = (
        settings.bird_database_url if bird else settings.readonly_database_url
    ).get_secret_value()
    cache_dir = CACHE_DIRS[options.dataset]
    fewshot = "fewshot" if options.fewshot else "nofewshot"
    evidence = "evidence" if options.evidence else "noevidence"
    schema = options.schema if options.schema == "full" else f"retrieved{options.k}"
    name = options.name or f"{options.dataset}_{options.model}_{schema}_{fewshot}_{evidence}"
    identity = {
        "provider": options.provider,
        "model": options.model,
        "reasoning_effort": "low",
        "structured_output": True,
    }

    inner = None
    if options.llm == "real":
        key = settings.gemini_api_key if options.provider == "gemini" else settings.groq_api_key
        if key is None:
            sys.exit(f"--llm real needs {options.provider.upper()}_API_KEY in api/.env")
        inner = OpenAICompatibleClient(
            base_url=PROVIDER_BASE_URLS[options.provider],
            api_key=key,
            model=options.model,
            reasoning_effort="low",
            timeout_s=120,
        )
    llm = CachedLLM(inner, cache_dir / "llm", identity)
    pacer = Pacer(REQUESTS_PER_MINUTE.get(options.model, 10))

    results_path = options.results_dir / f"{name}.jsonl"
    options.results_dir.mkdir(parents=True, exist_ok=True)
    done: dict[int, Record] = {}
    if results_path.exists():
        for line in results_path.read_text("utf-8").splitlines():
            record = Record(**json.loads(line))
            done[record.question_id] = record

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    app_pool: asyncpg.Pool[asyncpg.Record] | None = None
    embedder: Embedder | None = None
    if options.schema == "retrieved":
        app_pool = await asyncpg.create_pool(settings.app_database_url.get_secret_value())
        embedder = FastEmbedder(settings.embedding_model, settings.embedding_cache_dir)
    stopped = False
    try:
        databases = {q.db_id for q in questions}
        full_texts = {db: await describe_schema(pool, tables[db]) for db in databases}
        edges = {db: await foreign_key_edges(pool, tables[db]) for db in databases}

        async def prompt_schema(q: Question) -> tuple[str, int]:
            """The schema text for this question, and how many tables it holds."""
            if app_pool is None or embedder is None:
                return full_texts[q.db_id], len(tables[q.db_id])
            query = f"{q.question} {q.evidence}" if options.evidence else q.question
            found = await search_tables(app_pool, embedder, db_id=q.db_id, text=query, k=options.k)
            chosen = connect_tables(found, edges[q.db_id])
            text = await describe_schema(pool, frozenset(f"public.{t}" for t in chosen))
            return text, len(chosen)

        todo = [q for q in questions if q.question_id not in done]
        print(f"{name}: {len(questions)} questions, {len(done)} already done, {len(todo)} to go")
        with results_path.open("a", encoding="utf-8") as out:
            for index, q in enumerate(todo, 1):
                schema_text, tables_sent = await prompt_schema(q)
                try:
                    record = await score(
                        q,
                        llm=llm,
                        pacer=pacer,
                        pool=pool,
                        schema_text=schema_text,
                        tables_sent=tables_sent,
                        tables=tables[q.db_id],
                        options=options,
                        cache_dir=cache_dir,
                    )
                except StopRun:
                    stopped = True
                    left = len(todo) - index + 1
                    print(f"\nRate limit keeps coming back (daily limit?). {left} questions left.")
                    print("Progress is saved: run the same command again after the reset.")
                    break
                done[q.question_id] = record
                out.write(json.dumps(asdict(record)) + "\n")
                out.flush()
                mark = "✓" if record.correct else "✗"
                print(
                    f"[{index}/{len(todo)}] q{q.question_id} {q.db_id:<24} {mark} {record.status}"
                )
    finally:
        await pool.close()
        if app_pool is not None:
            await app_pool.close()
        await llm.aclose()

    records = [done[q.question_id] for q in questions if q.question_id in done]
    meta = {
        "name": name,
        "dataset": options.dataset,
        "model": options.model,
        "provider": options.provider,
        "options": {
            "schema": options.schema,
            "k": options.k if options.schema == "retrieved" else None,
            "correction": False,
            "fewshot": options.fewshot,
            "evidence": options.evidence,
        },
        "finished": not stopped and len(records) == len(questions),
        "date": datetime.now(UTC).date().isoformat(),
    }
    summary = summarize(records, meta)
    (options.results_dir / f"{name}.summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", "utf-8"
    )
    (options.results_dir / f"{name}.md").write_text(as_markdown(summary), "utf-8")
    print("\n" + as_markdown(summary))
    print(f"cache: {llm.hits} replayed, {llm.misses} live calls")

    if options.expect:
        expected = json.loads(options.expect.read_text("utf-8"))
        if (summary["ex"], summary["by_status"]) != (expected["ex"], expected["by_status"]):
            print(f"MISMATCH with {options.expect}")
            return 1
        print(f"matches {options.expect}")
    return 3 if stopped else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
