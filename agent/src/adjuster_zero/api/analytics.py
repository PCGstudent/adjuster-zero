"""KPI computation for the Analytics screen (blueprint Part 7).

STP rate, override rate, cost/claim, schema-violation rate, the funnel, the
confidence-calibration buckets (fed by approval resolutions), the RPD meter, and
the per-tool failure table — all derived from the event-sourced store.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .. import db
from .service import get_store

# Nominal token price (USD) for the cost-per-claim KPI. flash-lite is ~free on
# the tier; this lets the dashboard still show a non-zero, honest estimate.
_PRICE_PER_1K_TOKENS = 0.0001


async def compute() -> dict[str, Any]:
    store = get_store()
    claims = await store.list_claims()
    approvals = await store.list_all_approvals()
    tool_calls = await store.all_tool_calls()
    decisions = await store.all_decisions()
    usage = await db.rpd_usage_today()

    total = len(claims)
    by_workflow: dict[str, int] = defaultdict(int)
    by_state: dict[str, int] = defaultdict(int)
    for c in claims:
        by_workflow[c.get("workflow") or "—"] += 1
        by_state[c["state"]] += 1

    w1_closed = sum(1 for c in claims if c.get("workflow") == "W1" and c["state"] == "CLOSED")
    terminalish = sum(1 for c in claims if c["state"] in
                      {"CLOSED", "DENIED", "ESCALATED", "REVIEW_PENDING", "INFO_PENDING"})
    stp_rate = round(w1_closed / terminalish, 3) if terminalish else 0.0

    resolved = [a for a in approvals if a.get("status") in {"approved", "modified", "rejected"}]
    overrides = [a for a in resolved if a.get("status") in {"modified", "rejected"}]
    override_rate = round(len(overrides) / len(resolved), 3) if resolved else 0.0

    tokens = sum((u["tokens_in"] + u["tokens_out"]) for u in usage)
    cost = round(tokens / 1000 * _PRICE_PER_1K_TOKENS, 4)
    cost_per_claim = round(cost / total, 5) if total else 0.0

    repaired = sum(1 for d in decisions if (d.get("guardrails") or {}).get("repaired"))
    schema_violation_rate = round(repaired / len(decisions), 4) if decisions else 0.0

    # confidence calibration: bucket resolved approvals by predicted confidence,
    # agreement = approved (not modified/rejected).
    buckets: dict[str, dict[str, float]] = {}
    for a in resolved:
        conf = a.get("confidence")
        if conf is None:
            continue
        b = f"{int(float(conf) * 10) * 10}-{int(float(conf) * 10) * 10 + 10}%"
        d = buckets.setdefault(b, {"n": 0, "agree": 0, "conf_sum": 0.0})
        d["n"] += 1
        d["agree"] += 1 if a.get("status") == "approved" else 0
        d["conf_sum"] += float(conf)
    calibration = [
        {"bucket": b, "n": int(d["n"]),
         "predicted": round(d["conf_sum"] / d["n"], 3),
         "agreement": round(d["agree"] / d["n"], 3)}
        for b, d in sorted(buckets.items())
    ]

    # per-tool failure table
    tf: dict[str, dict[str, int]] = {}
    for t in tool_calls:
        td = tf.setdefault(t["tool"], {"total": 0, "errors": 0})
        td["total"] += 1
        if t.get("status") == "error":
            td["errors"] += 1
    tool_failures = [
        {"tool": k, "total": v["total"], "errors": v["errors"],
         "failure_rate": round(v["errors"] / v["total"], 3) if v["total"] else 0.0}
        for k, v in sorted(tf.items(), key=lambda kv: -kv[1]["errors"])
    ]

    return {
        "total_claims": total,
        "by_workflow": dict(by_workflow),
        "by_state": dict(by_state),
        "kpis": {
            "stp_rate": stp_rate,
            "override_rate": override_rate,
            "cost_per_claim_usd": cost_per_claim,
            "schema_violation_rate": schema_violation_rate,
            "tokens_today": tokens,
        },
        "funnel": {
            "received": total,
            "triaged": total - by_state.get("RECEIVED", 0),
            "auto_w1": by_workflow.get("W1", 0),
            "human_w2": by_workflow.get("W2", 0),
            "fraud_w3": by_workflow.get("W3", 0),
            "info_w4": by_workflow.get("W4", 0),
            "escalated_w5": by_workflow.get("W5", 0),
            "settled": by_state.get("CLOSED", 0),
        },
        "calibration": calibration,
        "rpd": usage,
        "tool_failures": tool_failures,
    }
