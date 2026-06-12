"""API smoke tests via FastAPI TestClient — no DB, no API key (offline planner,
in-memory store). Proves inject → run → CLOSED is reachable through HTTP and that
the queue/detail reads work."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from adjuster_zero.main import app


def test_scenarios_listed() -> None:
    with TestClient(app) as client:
        res = client.get("/api/scenarios")
        assert res.status_code == 200
        keys = {s["key"] for s in res.json()}
        assert {"clean_glass", "lapsed_policy", "missing_docs"} <= keys


def test_inject_clean_glass_runs_to_closed() -> None:
    with TestClient(app) as client:
        res = client.post("/api/claims/inject", json={"scenario_key": "clean_glass"})
        assert res.status_code == 200
        claim_id = res.json()["claim_id"]

        # The graph runs in a background task; poll the detail until terminal.
        state = None
        for _ in range(50):
            detail = client.get(f"/api/claims/{claim_id}").json()
            state = detail["claim"]["state"]
            if state in {"CLOSED", "ESCALATED", "REVIEW_PENDING"}:
                break
            time.sleep(0.05)
        assert state == "CLOSED"
        tools = [t["tool"] for t in detail["tool_calls"]]
        assert "payment_execute" in tools
        assert detail["claim"]["paid"] and detail["claim"]["paid"] > 0


def test_inject_unknown_scenario_400() -> None:
    with TestClient(app) as client:
        res = client.post("/api/claims/inject", json={"scenario_key": "nope"})
        assert res.status_code == 400
