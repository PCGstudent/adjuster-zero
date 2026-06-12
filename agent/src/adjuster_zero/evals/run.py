"""`make evals` / admin "Run evals" — replay the golden set through the real
graph, score route + terminal-state accuracy, write a report, and (with a DB)
record an eval_runs row.

Deterministic offline by default (no key, no RPD spend); uses real flash-lite
when GEMINI_API_KEY is set, guarded by the daily RPD budget.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from .. import db
from ..config import get_settings
from ..domain.aggregate import ClaimAggregate
from ..graph.lifecycle import LifecycleDeps, run_claim
from ..llm import get_client
from ..persistence import InMemoryClaimStore
from ..rag.embed import get_embedder
from ..rag.index import InMemoryGuidelineIndex
from ..router import RoutingConfig
from ..seed.data import CLAIM_HISTORY
from ..seed.offline import OfflineGeminiClient
from ..tools import RagContext, ToolExecutor, build_registry
from .golden import golden_claims

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Conservative free-tier daily ceiling for flash-lite (matches CLAUDE.md note).
_FLASH_LITE_RPD = 1000
_CALLS_PER_CLAIM = 2  # extract + classify (flash-lite)
REPORTS_DIR = Path(__file__).resolve().parents[4] / "evals" / "reports"


async def _rpd_guard(n_cases: int) -> tuple[bool, str]:
    """Refuse a real-model run that would exhaust the day's flash-lite budget."""
    usage = await db.rpd_usage_today()
    used = sum(u["requests"] for u in usage if "flash-lite" in u["model"])
    needed = n_cases * _CALLS_PER_CLAIM
    if used + needed > _FLASH_LITE_RPD:
        return False, f"would use {needed} flash-lite calls; {_FLASH_LITE_RPD - used} remain today"
    return True, "ok"


def _narratives() -> dict[str, list[tuple[str, str]]]:
    return {cid: [(c["claim_id"], c.get("narrative", "")) for c in cl]
            for cid, cl in CLAIM_HISTORY.items()}


async def run_evals(*, max_cases: int | None = None) -> dict[str, Any]:
    from langgraph.checkpoint.memory import MemorySaver

    cases = golden_claims()
    if max_cases:
        cases = cases[:max_cases]
    settings = get_settings()
    real = settings.gemini_configured

    if real:
        ok, reason = await _rpd_guard(len(cases))
        if not ok:
            return {"refused": True, "reason": reason}

    embedder = get_embedder()
    rag = RagContext(index=await InMemoryGuidelineIndex.build(embedder), embedder=embedder,
                     narratives=_narratives())

    confusion: dict[str, dict[str, int]] = {}
    route_hits = term_hits = 0
    rows: list[dict[str, Any]] = []
    for case in cases:
        store = InMemoryClaimStore()
        planner = get_client() if real else OfflineGeminiClient(case)
        executor = ToolExecutor(build_registry(rag), recorder=store.record_tool_call)
        deps = LifecycleDeps(store=store, planner=planner, executor=executor,
                             routing_config=RoutingConfig(), config_version=1,
                             ground_coverage=real)
        agg = ClaimAggregate(id=case.key, fnol_text=case.fnol_text,
                             claimant_id=case.claimant_id, policy_number=case.policy_number)
        final = await run_claim(agg, deps, checkpointer=MemorySaver(), thread_id=case.key)

        exp_r = case.ground_truth["expected_route"]
        exp_t = case.ground_truth["expected_terminal_state"]
        act_r = final.workflow.value if final.workflow else "?"
        act_t = final.state.value
        confusion.setdefault(exp_r, {}).setdefault(act_r, 0)
        confusion[exp_r][act_r] += 1
        route_ok = act_r == exp_r
        route_hits += route_ok
        term_hits += act_t == exp_t
        rows.append({"id": case.key, "expected_route": exp_r, "actual_route": act_r,
                     "expected_terminal": exp_t, "actual_terminal": act_t, "route_ok": route_ok})

    total = len(cases)
    ts = dt.datetime.now(dt.UTC).isoformat()
    report: dict[str, Any] = {
        "ts": ts,
        "model": "gemini-2.5-flash-lite" if real else "offline-deterministic",
        "total": total,
        "route_accuracy": round(route_hits / total, 4) if total else 0,
        "terminal_accuracy": round(term_hits / total, 4) if total else 0,
        "confusion": confusion,
        "cases": rows,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = ts.replace(":", "").replace("-", "")[:15]
    (REPORTS_DIR / f"eval_{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    await _persist_run(report)
    return report


async def _persist_run(report: dict[str, Any]) -> None:
    pool = db.get_pool()
    if pool is None:
        return
    from psycopg.types.json import Json

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO eval_runs (total, route_accuracy, terminal_accuracy, report) "
            "VALUES (%s,%s,%s,%s)",
            (report["total"], report["route_accuracy"], report["terminal_accuracy"], Json(report)),
        )


def main() -> None:
    async def _go() -> None:
        await db.open_pool()
        report = await run_evals()
        if report.get("refused"):
            print(f"Evals refused: {report['reason']}")
        else:
            print(f"Evals: route_accuracy={report['route_accuracy']:.2%} "
                  f"terminal_accuracy={report['terminal_accuracy']:.2%} "
                  f"over {report['total']} golden claims ({report['model']}).")
            print(f"Confusion: {json.dumps(report['confusion'])}")
        await db.close_pool()

    asyncio.run(_go())


if __name__ == "__main__":
    main()
