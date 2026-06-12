"""Router unit tests (Phase 1 acceptance: covers R-01, R-02, R-03, R-99).

The router is pure, so these run with no I/O. Table-driven where it helps.
"""

from __future__ import annotations

import pytest

from adjuster_zero.domain.states import Workflow
from adjuster_zero.router import RouterInput, RoutingConfig, route

CFG = RoutingConfig()


def _clean_w1() -> RouterInput:
    """A fully clean STP-eligible input (clean_glass)."""
    return RouterInput(
        completeness=1.0,
        min_field_confidence=0.96,
        policy_active=True,
        coverage_covered=True,
        coverage_confidence=0.94,
        clear_exclusion=False,
        fraud_score=0.08,
        severity=1,
        amount_est=412,
        classification_confidence=0.95,
    )


def test_r03_clean_glass_routes_w1() -> None:
    d = route(_clean_w1(), CFG)
    assert d.workflow is Workflow.W1
    assert d.rule_id == "R-03"


def test_r01_incomplete_routes_w4() -> None:
    inp = _clean_w1().model_copy(update={"completeness": 0.7})
    d = route(inp, CFG)
    assert d.workflow is Workflow.W4
    assert d.rule_id == "R-01"


def test_r01_low_field_confidence_routes_w4() -> None:
    inp = _clean_w1().model_copy(update={"min_field_confidence": 0.5})
    d = route(inp, CFG)
    assert d.rule_id == "R-01"
    assert d.workflow is Workflow.W4


def test_r02_lapsed_policy_routes_w2() -> None:
    inp = _clean_w1().model_copy(update={"policy_active": False, "coverage_covered": False})
    d = route(inp, CFG)
    assert d.workflow is Workflow.W2
    assert d.rule_id == "R-02"


def test_r02_clear_exclusion_routes_w2() -> None:
    inp = _clean_w1().model_copy(
        update={"clear_exclusion": True, "exclusion_confidence": 0.95, "coverage_covered": False}
    )
    d = route(inp, CFG)
    assert d.rule_id == "R-02"


def test_r02_weak_exclusion_does_not_fast_deny() -> None:
    # exclusion confidence below threshold should NOT trigger R-02
    inp = _clean_w1().model_copy(
        update={"clear_exclusion": True, "exclusion_confidence": 0.5}
    )
    d = route(inp, CFG)
    assert d.rule_id != "R-02"


def test_r99_default_routes_w2() -> None:
    # covered but expensive (above ceiling) and not otherwise special → default
    inp = _clean_w1().model_copy(update={"amount_est": 9000})
    d = route(inp, CFG)
    assert d.workflow is Workflow.W2
    assert d.rule_id == "R-99"


@pytest.mark.parametrize(
    "update,expected_rule",
    [
        ({"fraud_score": 0.5}, "R-99"),  # fraud band (R-04/06 land Phase 2) → default
        ({"severity": 4}, "R-99"),  # high severity (R-05 lands Phase 2) → default
        ({"coverage_covered": None}, "R-99"),  # coverage unknown → not STP
        ({"coverage_confidence": 0.6}, "R-99"),  # coverage conf below STP floor
        ({"classification_confidence": 0.5}, "R-99"),  # low class conf → not STP
    ],
)
def test_non_stp_inputs_fall_to_default(update: dict, expected_rule: str) -> None:
    d = route(_clean_w1().model_copy(update=update), CFG)
    assert d.rule_id == expected_rule
    assert d.workflow is Workflow.W2


def test_ceiling_is_config_driven() -> None:
    # raising the ceiling makes an otherwise-defaulted claim STP-eligible
    inp = _clean_w1().model_copy(update={"amount_est": 9000})
    assert route(inp, CFG).rule_id == "R-99"
    hi = RoutingConfig(auto_pay_ceiling=10000)
    assert route(inp, hi).rule_id == "R-03"


def test_rule_order_r01_beats_r03() -> None:
    # incomplete AND otherwise-clean must take R-01 (evaluated first)
    inp = _clean_w1().model_copy(update={"completeness": 0.5})
    assert route(inp, CFG).rule_id == "R-01"
