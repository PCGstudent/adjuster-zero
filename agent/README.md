# Adjuster Zero — Agent Service

FastAPI + LangGraph service. The **executor** (LangGraph state machine) is the
agent's spine; the LLM only proposes typed data. See repo root `CLAUDE.md` and
`docs/blueprint.md`.

## Local dev

```bash
uv sync --extra dev          # create venv + install
cp ../.env.example ../.env    # fill in keys
uv run uvicorn adjuster_zero.main:app --reload --port 8080
```

## Test / lint / typecheck

```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
```

## Layout

```
src/adjuster_zero/
  main.py        FastAPI app, /healthz, /debug/* endpoints
  config.py      typed settings (pydantic-settings, reads .env)
  db.py          psycopg connection pool + RPD-counter persistence
  llm/           GeminiClient: tiering, token-bucket limiter, structured output
  graph/         LangGraph graphs (hello-graph in Phase 0)
```
