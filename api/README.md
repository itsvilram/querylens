# QueryLens API

FastAPI backend for QueryLens. See the [main README](../README.md) for how to run everything.

```sh
uv sync                      # create .venv and install locked packages
uv run uvicorn app.main:app --reload   # dev server on http://127.0.0.1:8000
uv run pytest                # tests (integration tests need `docker compose up -d db redis`)
uv run ruff check . && uv run ruff format --check . && uv run mypy app tests eval scripts
```

## Endpoints

- `POST /api/ask`: `{"question": "...", "session_id": "<optional chat id>"}` → one JSON answer.
- `POST /api/ask/stream`: the same, as server-sent events: `stage` events
  (`rewrite`, `wait`, `retrieve`, `generate`, `correct`, `execute`), then one `answer` or `error`.
- `GET /api/stats`: answer-cache hits, misses and hit rate. `GET /api/health`: liveness.

Answers are cached in Redis for a day (key: the question after the follow-up rewrite + schema,
prompt, model and settings). Every request counts against a per-IP sliding-window limit
(10/minute, 100/hour by default). Cache speed with the real model:

```sh
LLM_MODE=real uv run python -m scripts.measure_cache   # → eval/results/cache_latency.json
```

## Evaluation (BIRD mini-dev)

```sh
uv run python -m scripts.download_bird   # ~230 MB of the 800 MB zip, into data/bird/ (git-ignored)
uv run python -m scripts.load_bird       # loads it into the bird_eval database (read-only role bird_ro)
uv run python -m eval.run --name B0      # 100 questions; replies are cached in data/eval_cache/
```

Schema retrieval (RAG):

```sh
uv run python -m scripts.index_schema    # embed table/column descriptions into app.schema_docs
uv run python -m eval.retrieval          # recall vs the gold SQL's tables (no LLM calls)
uv run python -m eval.run --name B0R --schema retrieved --k 4
uv run python -m eval.compare B0 B0R     # question by question: fixed, broken, p-value
```

A run stopped by the daily API limit resumes where it stopped: run the same command again.
Results: `eval/results/<name>.md` (summary) and `.jsonl` (one line per question).
BIRD mini-dev is CC BY-SA 4.0: it is downloaded, never committed. Only question ids are
committed (`eval/subset_ids.json`).
```
