# QueryLens

Ask a database questions in plain English. QueryLens writes the SQL, checks that it is safe, runs it as a read-only user, and shows the SQL, a table and a chart. You can ask follow-up questions.

> **Work in progress.** Every number in this README will come from the eval output files. None are measured yet.

## What makes it more than an LLM wrapper

- **Measured accuracy** on a public benchmark (BIRD mini-dev), with ablations.
- **SQL security in layers:** a read-only database role, read-only transactions, timeouts, and an AST validator. The prompt is not a security layer.
- **Schema retrieval (RAG)** and **self-correction**, both measured.
- **Redis** caching and rate limiting.

## Stack

Vue 3 (Composition API) + TypeScript + Vite · Python 3.12 + FastAPI · PostgreSQL 18 + pgvector · Redis · Gemini API (free tier)

## Run it locally

You need Docker Desktop, [uv](https://docs.astral.sh/uv/) and Node 24.

```sh
docker compose up -d                  # Postgres with the Pagila demo data, and Redis
cp api/.env.example api/.env          # then fill in your own values

cd api && uv sync && uv run uvicorn app.main:app --reload    # API on :8000
cd web && npm install && npm run dev                          # app on http://localhost:5173
```

Or run everything in Docker: `docker compose --profile full up -d --build`, then open http://localhost:8080.

## Layout

```
api/        FastAPI backend (Python 3.12, uv)
web/        Vue 3 frontend (TypeScript, Vite, Tailwind)
db/         Postgres image: Pagila demo data + the read-only role
.github/    CI: lint, type-check, tests, build
```

## Credits

- [Pagila](https://github.com/devrimgunduz/pagila) sample database (v4.1.1), PostgreSQL licence.
