# QueryLens API

FastAPI backend for QueryLens. See the [main README](../README.md) for how to run everything.

```sh
uv sync                      # create .venv and install locked packages
uv run uvicorn app.main:app --reload   # dev server on http://127.0.0.1:8000
uv run pytest                # tests (integration tests need `docker compose up -d db redis`)
uv run ruff check . && uv run ruff format --check . && uv run mypy app tests eval scripts
```

## Evaluation (BIRD mini-dev)

```sh
uv run python -m scripts.download_bird   # ~230 MB of the 800 MB zip, into data/bird/ (git-ignored)
uv run python -m scripts.load_bird       # loads it into the bird_eval database (read-only role bird_ro)
uv run python -m eval.run --name B0      # 100 questions; replies are cached in data/eval_cache/
```

A run stopped by the daily API limit resumes where it stopped: run the same command again.
Results: `eval/results/<name>.md` (summary) and `.jsonl` (one line per question).
BIRD mini-dev is CC BY-SA 4.0: it is downloaded, never committed. Only question ids are
committed (`eval/subset_ids.json`).
```
