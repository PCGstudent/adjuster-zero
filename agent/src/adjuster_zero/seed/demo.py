"""`make demo` — run the Phase demo journeys end-to-end through the REAL graph
and print the timeline. Uses the offline deterministic planner (no API key
needed); set GEMINI_API_KEY to exercise the real model instead.

Runs against an in-memory store (no DB writes) so it is a safe, repeatable proof
of the lifecycle. The live dashboard demo uses the API + Supabase Realtime.
"""

from __future__ import annotations

import asyncio
import sys

# Windows consoles default to cp1252; force UTF-8 so the timeline prints cleanly.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ..config import get_settings
from ..domain.aggregate import ClaimAggregate
from ..graph.lifecycle import LifecycleDeps, run_claim
from ..llm import get_client
from ..persistence import InMemoryClaimStore
from ..router import RoutingConfig
from ..tools import ToolExecutor, build_registry
from .data import SCENARIOS, Scenario, get_scenario
from .offline import OfflineGeminiClient


async def run_scenario(scenario: Scenario) -> None:
    store = InMemoryClaimStore()
    settings = get_settings()
    planner = get_client() if settings.gemini_configured else OfflineGeminiClient(scenario)
    executor = ToolExecutor(build_registry(), recorder=store.record_tool_call)
    deps = LifecycleDeps(
        store=store, planner=planner, executor=executor,
        routing_config=RoutingConfig(), config_version=1,
    )
    agg = ClaimAggregate(
        id=f"CLM-DEMO-{scenario.key}",
        fnol_text=scenario.fnol_text,
        document_ids=scenario.document_ids,
        claimant_id=scenario.claimant_id,
        policy_number=scenario.policy_number,
    )
    # W2/W4 pause at a human gate (interrupt) → a checkpointer is required.
    from langgraph.checkpoint.memory import MemorySaver

    final = await run_claim(agg, deps, checkpointer=MemorySaver())

    print(f"\n=== {scenario.title} ({scenario.key}) ===")
    for e in store.events:
        print(f"  - {e['type']:<22} {e['data']}")
    print(f"  tools: {[t['tool'] for t in store.tool_calls]}")
    print(
        f"  -> route={final.workflow.value if final.workflow else '-'} "
        f"rule={final.rule_id} state={final.state.value} paid=${final.financials.paid}"
    )
    expected = scenario.ground_truth.get("expected_terminal_state")
    print(f"  expected terminal ~ {expected}")


async def main_async(keys: list[str]) -> None:
    scenarios = [get_scenario(k) for k in keys] if keys else SCENARIOS
    for s in scenarios:
        if s is not None:
            await run_scenario(s)


def main() -> None:
    asyncio.run(main_async(sys.argv[1:]))


if __name__ == "__main__":
    main()
