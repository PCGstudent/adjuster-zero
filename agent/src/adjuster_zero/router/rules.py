"""The routing rule table as a pure function.

Phase 1 implements R-01, R-02, R-03 and the R-99 default; every other condition
falls through to R-99 (W2 Standard). Phase 2 fills in R-00/R-04/R-05/R-06.

Purity is the feature: no I/O, no LLM, no clock. Thresholds arrive as a
``RoutingConfig`` loaded from the versioned ``config`` table, so policy changes
are testable against history and reproducible per ``config_version``.
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


class RoutingDecision(BaseModel):
    workflow: Workflow
    rule_id: str
    rationale: str
    inputs: dict[str, object] = Field(default_factory=dict)


def route(inp: RouterInput, cfg: RoutingConfig) -> RoutingDecision:
    """Evaluate rules top-down, first match wins. Pure."""
    snapshot = inp.model_dump()

    def decision(workflow: Workflow, rule_id: str, rationale: str) -> RoutingDecision:
        return RoutingDecision(
            workflow=workflow, rule_id=rule_id, rationale=rationale, inputs=snapshot
        )

    # R-01 — incomplete or low-confidence extraction → Information Request (W4)
    if inp.completeness < cfg.completeness_min or inp.min_field_confidence < cfg.field_conf_min:
        return decision(
            Workflow.W4,
            "R-01",
            f"completeness {inp.completeness:.2f} < {cfg.completeness_min} "
            f"or field conf {inp.min_field_confidence:.2f} < {cfg.field_conf_min} -> info request",
        )

    # R-02 — policy inactive at loss OR clear exclusion → fast-deny review (W2)
    if not inp.policy_active or (
        inp.clear_exclusion and inp.exclusion_confidence >= cfg.exclusion_conf_min
    ):
        why = "policy inactive at loss date" if not inp.policy_active else "clear exclusion"
        return decision(Workflow.W2, "R-02", f"{why} -> fast-deny, human review")

    # R-03 — clean, cheap, low-severity, covered → Straight-Through Processing (W1)
    if (
        inp.fraud_score < cfg.fraud_low
        and inp.severity <= cfg.severity_stp_max
        and inp.amount_est <= cfg.auto_pay_ceiling
        and inp.coverage_covered is True
        and inp.coverage_confidence >= cfg.coverage_conf_min
        and inp.classification_confidence >= cfg.stp_confidence_min
    ):
        return decision(
            Workflow.W1,
            "R-03",
            f"fraud {inp.fraud_score:.2f}<{cfg.fraud_low}, sev {inp.severity}<="
            f"{cfg.severity_stp_max}, amount {inp.amount_est:.0f}<={cfg.auto_pay_ceiling:.0f}, "
            f"coverage conf {inp.coverage_confidence:.2f}>={cfg.coverage_conf_min} -> auto-pay",
        )

    # R-99 — default → Standard Adjudication (W2)
    return decision(Workflow.W2, "R-99", "no specific rule matched → standard adjudication")
