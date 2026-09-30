# QueryLens API

FastAPI backend for QueryLens. See the [main README](../README.md) for how to run everything.

```sh
uv sync                      # create .venv and install locked packages
uv run uvicorn app.main:app --reload   # dev server on http://127.0.0.1:8000
uv run pytest                # tests
uv run ruff check . && uv run ruff format --check . && uv run mypy app tests
```
