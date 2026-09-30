# syntax=docker/dockerfile:1
FROM python:3.12-slim

# uv, pinned, copied from its official image.
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /uvx /bin/

WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1

# Install locked dependencies first: this layer is cached until the lock file changes.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project

COPY app ./app

# Run as a normal user, not root.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["/srv/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
