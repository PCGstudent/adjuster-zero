"""The golden claim set — 50 labeled synthetic claims spanning all five routes.

Each case is a Scenario (so the offline planner can replay it deterministically)
with ground_truth carrying the expected route + terminal state + key fields.
"""

from __future__ import annotations

from ..seed.data import Scenario

GoldenClaim = Scenario


def _case(
    n: int, *, policy: str | None, claimant: str, peril: str, severity: int,
    route: str, terminal: str, complete: bool = True, text: str | None = None,
) -> Scenario:
    body = text or f"Synthetic {peril} loss for evaluation case {n}."
    return Scenario(
        key=f"GOLD-{n:03d}",
        title=f"Golden {n:03d} ({route})",
        fnol_text=body + (f" Policy {policy}." if policy else " (no policy number provided)"),
        policy_number=policy,
        claimant_id=claimant,
        document_ids=[],
        loss_date="2026-06-05" if complete else "",
        ground_truth={
            "expected_route": route, "expected_terminal_state": terminal,
            "peril": peril, "severity": severity,
        },
    )


def golden_claims() -> list[Scenario]:
    cases: list[Scenario] = []
    n = 0
    active = ["POL-88341", "POL-90013", "POL-55200"]

    # W1 STP — clean glass, low severity, covered, cheap (×12)
    for i in range(12):
        n += 1
        cases.append(_case(n, policy=active[i % 3], claimant="CLMT-001", peril="glass",
                            severity=1, route="W1", terminal="CLOSED"))

    # W2 R-99 — collision above the auto-pay ceiling, covered (×8)
    for i in range(8):
        n += 1
        cases.append(_case(n, policy=active[i % 3], claimant="CLMT-003", peril="collision",
                            severity=2, route="W2", terminal="REVIEW_PENDING"))

    # W2 R-02 — lapsed policy fast-deny (×8)
    for _ in range(8):
        n += 1
        cases.append(_case(n, policy="POL-77120", claimant="CLMT-002", peril="glass",
                            severity=1, route="W2", terminal="REVIEW_PENDING"))

    # W4 R-01 — missing information (×8)
    for _ in range(8):
        n += 1
        cases.append(_case(n, policy=None, claimant="CLMT-003", peril="other", severity=2,
                            route="W4", terminal="INFO_PENDING", complete=False,
                            text="I had an incident and want to file a claim."))

    # W5 R-05 — high severity collision (×7)
    for i in range(7):
        n += 1
        cases.append(_case(n, policy=active[i % 3], claimant="CLMT-001", peril="collision",
                            severity=4, route="W5", terminal="ESCALATED"))

    # W3 — fraud suspect (exact-duplicate theft narrative) (×7)
    for _ in range(7):
        n += 1
        cases.append(_case(
            n, policy="POL-55200", claimant="CLMT-004", peril="theft", severity=2,
            route="W3", terminal="ESCALATED",
            text="My parked car was broken into overnight in the driveway and my laptop "
                 "bag and tools were stolen from the trunk."))

    return cases  # 12+8+8+8+7+7 = 50
