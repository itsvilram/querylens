"""Measure the answer cache: server time for a miss vs a hit, with the configured model.

Runs the app in-process with the settings from api/.env (use LLM_MODE=real),
on its own Redis database (14, emptied first), without the rate limit. Asks
each question once (a miss: LLM + database) and then HITS more times (hits),
and reports the server-side time (the answer's elapsed_ms). Costs one LLM
call per question.

    uv run python -m scripts.measure_cache
"""

import argparse
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from redis import Redis

from app.config import Settings
from app.main import create_app

QUESTIONS = [
    "Which film categories made the most money in 2024?",
    "How many rentals were there each month in 2024?",
    "How many films are there?",
    "Which 10 customers spent the most?",
    "Which actors appear in the most films?",
]
HITS = 5
REDIS_URL = "redis://127.0.0.1:6379/14"  # not the app's database 0, not the tests' 15
RESULTS = Path(__file__).resolve().parents[1] / "eval" / "results" / "cache_latency.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args()

    Redis.from_url(REDIS_URL).flushdb()
    settings = Settings(redis_url=REDIS_URL, rate_limit_per_minute=0, rate_limit_per_hour=0)
    rows = []
    with TestClient(create_app(settings)) as client:
        for question in QUESTIONS:
            times = []
            for _ in range(1 + HITS):
                response = client.post("/api/ask", json={"question": question})
                response.raise_for_status()
                body = response.json()
                times.append((body["cache"], body["elapsed_ms"]))
            statuses = [status for status, _ in times]
            if statuses != ["miss"] + ["hit"] * HITS:
                raise SystemExit(f"expected one miss, then hits; got {statuses} for {question!r}")
            rows.append(
                {
                    "question": question,
                    "miss_ms": times[0][1],
                    "hit_ms_median": statistics.median(ms for _, ms in times[1:]),
                }
            )

    miss = statistics.median(r["miss_ms"] for r in rows)
    hit = statistics.median(r["hit_ms_median"] for r in rows)
    model = settings.model_for(settings.llm_provider)  # the default model answers
    print(f"model: {model} (LLM_MODE={settings.llm_mode})\n")
    print("| Question | Miss (ms) | Hit, median of 5 (ms) |\n|---|---:|---:|")
    for r in rows:
        print(f"| {r['question']} | {r['miss_ms']:.0f} | {r['hit_ms_median']:.1f} |")
    print(f"\nMedian: miss {miss:.0f} ms, hit {hit:.1f} ms ({miss / hit:.0f}x faster).")

    args.out.write_text(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "llm_mode": settings.llm_mode,
                "model": model,
                "hits_per_question": HITS,
                "median_miss_ms": miss,
                "median_hit_ms": hit,
                "questions": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
