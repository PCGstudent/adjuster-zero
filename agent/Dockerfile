# Cloud Run-ready image. Uses uv for fast, reproducible installs.
FROM python:3.12-slim AS base

# uv: copy the static binary from the official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (cached layer) using only the lockfile + manifest.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project --frozen 2>/dev/null || uv sync --no-dev --no-install-project

# Now the source.
COPY src ./src
RUN uv sync --no-dev --no-install-project

ENV PATH="/app/.venv/bin:$PATH"

# Cloud Run provides $PORT; default to 8080 locally.
ENV PORT=8080
EXPOSE 8080

# Launch via the package entrypoint (sets the event-loop policy cross-platform).
CMD ["python", "-m", "adjuster_zero"]
