"""Synthetic policies, claimants, and FNOL scenarios with ground truth.

All names/numbers are invented. The mock external systems (policy_lookup etc.)
read POLICIES/CLAIMANTS; the demo and evals inject SCENARIOS.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── Mock policy-admin system ─────────────────────────────────────────────────
POLICIES: dict[str, dict[str, Any]] = {
    "POL-88341": {
        "policy_id": "pol_88341",
        "status": "active",
        "holder": "J. Ortiz",
        "effective_from": "2025-01-01",
        "effective_to": "2026-12-31",
        "coverages": [
            {"code": "AUTO-COMP", "limit": 50000, "deductible": 0},
            {"code": "AUTO-COLL", "limit": 50000, "deductible": 500},
        ],
        "endorsements": ["GLASS-ZERO-DED"],
    },
    "POL-77120": {
        "policy_id": "pol_77120",
        "status": "lapsed",
        "holder": "M. Reyes",
        "effective_from": "2025-01-01",
        "effective_to": "2026-06-02",  # lapsed 6 days before the loss
        "coverages": [
            {"code": "AUTO-COMP", "limit": 40000, "deductible": 100},
        ],
        "endorsements": [],
    },
    "POL-90013": {
        "policy_id": "pol_90013",
        "status": "active",
        "holder": "K. Singh",
        "effective_from": "2025-03-01",
        "effective_to": "2027-02-28",
        "coverages": [
            {"code": "AUTO-COMP", "limit": 60000, "deductible": 250},
            {"code": "AUTO-COLL", "limit": 60000, "deductible": 500},
        ],
        "endorsements": [],
    },
    "POL-55200": {
        "policy_id": "pol_55200",
        "status": "active",
        "holder": "D. Frost",
        "effective_from": "2024-01-01",
        "effective_to": "2027-12-31",
        "coverages": [
            {"code": "AUTO-COMP", "limit": 70000, "deductible": 250},
            {"code": "AUTO-COLL", "limit": 70000, "deductible": 500},
        ],
        "endorsements": [],
    },
}

CLAIMANTS: dict[str, dict[str, Any]] = {
    "CLMT-001": {"name": "J. Ortiz", "dob": "1986-04-12", "since": "2020-01-01"},
    "CLMT-002": {"name": "M. Reyes", "dob": "1979-11-30", "since": "2019-06-01"},
    "CLMT-003": {"name": "K. Singh", "dob": "1992-08-05", "since": "2022-03-01"},
    "CLMT-004": {"name": "D. Frost", "dob": "1990-02-22", "since": "2024-01-01"},
}


# Mock prior-claims history (for claim_history / duplicate_claim_check / fraud).
# Phase 1/2 claimants are clean; the fraud_suspect claimant is seeded in Phase 3.
CLAIM_HISTORY: dict[str, list[dict[str, Any]]] = {
    "CLMT-001": [],
    "CLMT-002": [
        {"claim_id": "CLM-2025-04412", "date": "2025-02-10", "peril": "collision",
         "paid": 1800, "narrative": "Rear-ended at a stop light, bumper damage."},
    ],
    "CLMT-003": [],
    # fraud_suspect: 3 prior claims in the window, one a near-duplicate narrative.
    "CLMT-004": [
        {"claim_id": "CLM-2025-09112", "date": "2025-09-03", "peril": "theft",
         "paid": 6200,
         "narrative": "My parked car was broken into overnight in the driveway and "
                      "my laptop bag and tools were stolen from the trunk."},
        {"claim_id": "CLM-2026-01187", "date": "2026-01-15", "peril": "glass",
         "paid": 380, "narrative": "Windshield cracked by a rock on the freeway."},
        {"claim_id": "CLM-2026-03340", "date": "2026-03-22", "peril": "collision",
         "paid": 2400, "narrative": "Backed into a pole in a parking lot, dented rear panel."},
    ],
}

# Claimants whose policy limit was raised shortly before the loss (fraud signal).
RECENT_COVERAGE_INCREASE: set[str] = {"CLMT-004"}


class Scenario(BaseModel):
    key: str
    title: str
    fnol_text: str
    policy_number: str | None
    claimant_id: str
    document_ids: list[str] = Field(default_factory=list)
    loss_date: str
    ground_truth: dict[str, Any]


SCENARIOS: list[Scenario] = [
    Scenario(
        key="clean_glass",
        title="Clean glass claim (auto-settle)",
        fnol_text=(
            "A rock hit my windshield on I-80 near Sacramento yesterday and cracked "
            "the glass. No other damage, nobody hurt. My policy number is POL-88341. "
            "Photo of the crack attached."
        ),
        policy_number="POL-88341",
        claimant_id="CLMT-001",
        document_ids=["photo_windshield_1.jpg"],
        loss_date="2026-06-08",
        ground_truth={
            "expected_route": "W1",
            "expected_terminal_state": "CLOSED",
            "peril": "glass",
            "severity": 1,
            "covered": True,
        },
    ),
    Scenario(
        key="lapsed_policy",
        title="Lapsed policy (refusal → human review)",
        fnol_text=(
            "A rock cracked my windshield on the highway two days ago. Nobody was hurt. "
            "Policy POL-77120. Please process my glass claim."
        ),
        policy_number="POL-77120",
        claimant_id="CLMT-002",
        document_ids=["photo_windshield_2.jpg"],
        loss_date="2026-06-08",
        ground_truth={
            "expected_route": "W2",
            "expected_terminal_state": "REVIEW_PENDING",
            "peril": "glass",
            "covered": False,
            "reason": "policy lapsed before loss date",
        },
    ),
    Scenario(
        key="missing_docs",
        title="Missing information (information-request loop)",
        fnol_text=(
            "Hi, I had an accident and my car is damaged. I want to file a claim. "
            "Let me know what you need."
        ),
        policy_number=None,  # no policy number provided → incomplete
        claimant_id="CLMT-003",
        document_ids=[],
        loss_date="",
        ground_truth={
            "expected_route": "W4",
            "expected_terminal_state": "INFO_PENDING",
            "reason": "completeness below threshold; missing policy number, loss date, location",
        },
    ),
    Scenario(
        key="fraud_suspect",
        title="Fraud suspect (route to SIU)",
        fnol_text=(
            "My car was broken into overnight while it was parked in my driveway, and "
            "my laptop bag and some tools were stolen out of the trunk again. Policy "
            "POL-55200. Please open a theft claim."
        ),
        policy_number="POL-55200",
        claimant_id="CLMT-004",
        document_ids=[],
        loss_date="2026-06-08",
        ground_truth={
            "expected_route": "W3",
            "expected_terminal_state": "ESCALATED",
            "peril": "theft",
            "severity": 2,
            "reason": "near-duplicate narrative + recent coverage increase + 3 prior claims",
        },
    ),
]


def get_scenario(key: str) -> Scenario | None:
    return next((s for s in SCENARIOS if s.key == key), None)
