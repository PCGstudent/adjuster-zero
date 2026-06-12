"""`make seed` — write the synthetic policies/claimants/scenarios to db/seeds/
as JSON (for inspection and the Phase 4 eval golden set) and print a summary.

This does NOT touch Supabase: the mock external systems are in-process Python.
The agent injects scenarios via the API; this just materializes the data.
"""

from __future__ import annotations

import json
from pathlib import Path

from .data import CLAIMANTS, POLICIES, SCENARIOS


def main() -> None:
    out = Path(__file__).resolve().parents[4] / "db" / "seeds"
    out.mkdir(parents=True, exist_ok=True)

    (out / "policies.json").write_text(json.dumps(POLICIES, indent=2), encoding="utf-8")
    (out / "claimants.json").write_text(json.dumps(CLAIMANTS, indent=2), encoding="utf-8")
    (out / "scenarios.json").write_text(
        json.dumps([s.model_dump() for s in SCENARIOS], indent=2), encoding="utf-8"
    )

    print(f"Wrote seeds to {out}")
    print(f"  policies:  {len(POLICIES)}")
    print(f"  claimants: {len(CLAIMANTS)}")
    print(f"  scenarios: {len(SCENARIOS)} -> {[s.key for s in SCENARIOS]}")


if __name__ == "__main__":
    main()
