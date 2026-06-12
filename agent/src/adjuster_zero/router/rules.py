"""The full routing rule table R-00..R-99 as a pure function.

Evaluated top-down, first match wins (blueprint Part 2). Purity is the feature:
no I/O, no LLM, no clock. The only band that needs the LLM is R-06 (0.30–0.70
fraud); the pure function flags it (`needs_tiebreak=True`) and returns the
conservative W2 default — the Phase 3 tiebreak node may override within the band
using guideline RAG, and that override is logged with alternatives.

Thresholds arrive as a ``RoutingConfig`` loaded from the versioned ``config``
table, so policy changes are testable against history and reproducible per
``config_version``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..domain.states import Workflow


class RoutingConfig(BaseModel):
    """Thresholds, loaded from config table value JSON (key='routing')."""

    auto_pay_ceiling: float = 2500
    fraud_low: float = 0.30
    fraud_high: float = 0.70
    severity_stp_max: int = 2
    coverage_conf_min: float = 0.85
    stp_confidence_min: float = 0.85
    completeness_min: float = 0.90
    field_conf_min: float = 0.80
    exclusion_conf_min: float = 0.90
    high_severity_min: int = 4
    high_amount_min: float = 25000
    coverage_conf_low: float = 0.60


class RouterInput(BaseModel):
    """Typed routing inputs — produced by the planner (LLM) + read-only tools,
    never by the router itself."""

    completeness: float = 0.0
    min_field_confidence: float = 1.0
    policy_active: bool = True
    coverage_covered: bool | None = None
    coverage_confidence: float = 0.0
    clear_exclusion: bool = False
    exclusion_confidence: float = 0.0
    fraud_score: float = 0.0
    severity: int = 3
    amount_est: float = 0.0
    classification_confidence: float = 0.0
    injury_flag: bool = False
    attorney_flag: bool = False
    # hard fraud signals (R-00)
    watchlist_hit: bool = False
    duplicate_hard_match: bool = False


class RoutingDecision(BaseModel):
    workflow: Workflow
    rule_id: str
    rationale: str
    needs_tiebreak: bool = False  # R-06 band: Phase 3 LLM override may apply
    inputs: dict[str, object] = Field(default_factory=dict)


def route(inp: RouterInput, cfg: RoutingConfig) -> RoutingDecision:
    """Evaluate rules top-down, first match wins. Pure."""
    snapshot = inp.model_dump()

    def d(workflow: Workflow, rule_id: str, rationale: str, *, tiebreak: bool = False) -> RoutingDecision:
        return RoutingDecision(
            workflow=workflow, rule_id=rule_id, rationale=rationale,
            needs_tiebreak=tiebreak, inputs=snapshot,
        )

    # R-00 — hard fraud signal: watchlist hit or duplicate-claim hard match → W3
    if inp.watchlist_hit or inp.duplicate_hard_match:
        why = "watchlist hit" if inp.watchlist_hit else "duplicate-claim hard match"
        return d(Workflow.W3, "R-00", f"{why} -> fraud investigation (no payment path)")

    # R-01 — incomplete or low-confidence extraction → Information Request (W4)
    if inp.completeness < cfg.completeness_min or inp.min_field_confidence < cfg.field_conf_min:
        return d(
            Workflow.W4, "R-01",
            f"completeness {inp.completeness:.2f} < {cfg.completeness_min} or field conf "
            f"{inp.min_field_confidence:.2f} < {cfg.field_conf_min} -> info request",
        )

    # R-02 — policy inactive at loss OR clear exclusion → fast-deny review (W2)
    if not inp.policy_active or (
        inp.clear_exclusion and inp.exclusion_confidence >= cfg.exclusion_conf_min
    ):
        why = "policy inactive at loss date" if not inp.policy_active else "clear exclusion"
        return d(Workflow.W2, "R-02", f"{why} -> fast-deny, human review")

    # R-03 — clean, cheap, low-severity, covered → Straight-Through Processing (W1)
    if (
        inp.fraud_score < cfg.fraud_low
        and inp.severity <= cfg.severity_stp_max
        and inp.amount_est <= cfg.auto_pay_ceiling
        and inp.coverage_covered is True
        and inp.coverage_confidence >= cfg.coverage_conf_min
        and inp.classification_confidence >= cfg.stp_confidence_min
        and not inp.injury_flag
        and not inp.attorney_flag
    ):
        return d(
            Workflow.W1, "R-03",
            f"fraud {inp.fraud_score:.2f}<{cfg.fraud_low}, sev {inp.severity}<="
            f"{cfg.severity_stp_max}, amount {inp.amount_est:.0f}<={cfg.auto_pay_ceiling:.0f}, "
            f"coverage conf {inp.coverage_confidence:.2f}>={cfg.coverage_conf_min} -> auto-pay",
        )

    # R-04 — fraud score above the high threshold → Fraud Investigation (W3)
    if inp.fraud_score > cfg.fraud_high:
        return d(Workflow.W3, "R-04", f"fraud {inp.fraud_score:.2f} > {cfg.fraud_high} -> SIU")

    # R-05 — high severity / injury / large amount / attorney / weak coverage → W5
    if (
        inp.severity >= cfg.high_severity_min
        or inp.injury_flag
        or inp.amount_est > cfg.high_amount_min
        or inp.attorney_flag
        or (inp.coverage_covered is not None and inp.coverage_confidence < cfg.coverage_conf_low)
    ):
        reasons = []
        if inp.severity >= cfg.high_severity_min:
            reasons.append(f"severity {inp.severity}>={cfg.high_severity_min}")
        if inp.injury_flag:
            reasons.append("injury")
        if inp.amount_est > cfg.high_amount_min:
            reasons.append(f"amount {inp.amount_est:.0f}>{cfg.high_amount_min:.0f}")
        if inp.attorney_flag:
            reasons.append("attorney")
        if inp.coverage_covered is not None and inp.coverage_confidence < cfg.coverage_conf_low:
            reasons.append(f"coverage conf {inp.coverage_confidence:.2f}<{cfg.coverage_conf_low}")
        return d(Workflow.W5, "R-05", "high-severity escalation: " + ", ".join(reasons))

    # R-06 — ambiguous fraud band → LLM tiebreak (Phase 3); conservative W2 default
    if cfg.fraud_low <= inp.fraud_score <= cfg.fraud_high:
        return d(
            Workflow.W2, "R-06",
            f"fraud {inp.fraud_score:.2f} in ambiguous band "
            f"[{cfg.fraud_low}, {cfg.fraud_high}] -> tiebreak (conservative W2)",
            tiebreak=True,
        )

    # R-99 — default → Standard Adjudication (W2)
    return d(Workflow.W2, "R-99", "no specific rule matched -> standard adjudication")
