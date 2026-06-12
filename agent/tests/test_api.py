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


def _wait_state(client: TestClient, claim_id: str, targets: set[str]) -> str:
    for _ in range(60):
        state = client.get(f"/api/claims/{claim_id}").json()["claim"]["state"]
        if state in targets:
            return state
        time.sleep(0.05)
    return state


def test_journey_b_lapsed_review_then_approve_denies() -> None:
    with TestClient(app) as client:
        claim_id = client.post("/api/claims/inject", json={"scenario_key": "lapsed_policy"}).json()[
            "claim_id"
        ]
        assert _wait_state(client, claim_id, {"REVIEW_PENDING"}) == "REVIEW_PENDING"

        # one pending approval (a denial) is waiting in the inbox
        approvals = client.get("/api/approvals").json()
        appr = next(a for a in approvals if a["claim_id"] == claim_id)
        assert appr["requested_action"]["type"] == "deny"

        # operator approves → claim resumes → DENIED
        res = client.post(f"/api/approvals/{appr['id']}/resolve", json={"resolution": "approve"})
        assert res.status_code == 200
        assert _wait_state(client, claim_id, {"DENIED"}) == "DENIED"
