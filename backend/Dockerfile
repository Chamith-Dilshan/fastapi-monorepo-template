# syntax=docker/dockerfile:1

# ---- build stage: resolve and install dependencies into a virtualenv ----
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first, on their own layer: editing application code doesn't
# invalidate this, so rebuilds stay fast.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ---- runtime stage: no uv, no build tooling, not root ----
FROM python:3.14-slim

RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # gunicorn reads this natively as its default worker count.
    WEB_CONCURRENCY=4

COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app scripts ./scripts

USER app
EXPOSE 8000

# uvicorn.workers is deprecated; uvicorn-worker is its maintained successor.
CMD ["gunicorn", "app.main:app", "-k", "uvicorn_worker.UvicornWorker", "-b", "0.0.0.0:8000"]
