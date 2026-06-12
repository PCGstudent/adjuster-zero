# Adjuster Zero — developer task runner.
# CI (Ubuntu) and macOS/Linux/Git-Bash have `make`. On Windows without make,
# run the underlying commands directly (see each target) or use Git Bash/WSL.

.PHONY: help dev dev-agent dev-web test test-agent lint lint-agent lint-web \
        typecheck seed demo evals install

help:
	@echo "Targets: install dev test lint typecheck seed demo evals"

install:        ## install all deps (agent venv + web node_modules)
	cd agent && uv sync --extra dev
	cd web && npm install

dev:            ## run agent (8080) and web (3000) together
	@echo "Starting agent + web. Use two terminals, or run dev-agent / dev-web."
	$(MAKE) -j2 dev-agent dev-web

dev-agent:
	cd agent && uv run uvicorn adjuster_zero.main:app --reload --port 8080

dev-web:
	cd web && npm run dev

test: test-agent ## run all tests

test-agent:
	cd agent && uv run pytest -q

lint: lint-agent lint-web

lint-agent:
	cd agent && uv run ruff check .

lint-web:
	cd web && npm run lint

typecheck:
	cd agent && uv run mypy src

seed:           ## generate + load synthetic policies/claimants/FNOLs (Phase 1+)
	cd agent && uv run python -m adjuster_zero.seed.run

ingest:         ## chunk + embed the guideline corpus into pgvector (Phase 3)
	cd agent && uv run python -m adjuster_zero.rag.ingest

demo:           ## run the phase demo journey end-to-end (Phase 1+)
	cd agent && uv run python -m adjuster_zero.seed.demo

evals:          ## replay the golden set through the graph (Phase 4)
	cd agent && uv run python -m adjuster_zero.evals.run
