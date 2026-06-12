"""Exhaustive, table-driven router tests for R-00..R-99 (Phase 2 acceptance).

The router is pure → no I/O. Each rule has at least one positive case plus
order/precedence and config-driven checks.
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
        fraud_score=0.08,
        severity=1,
        amount_est=412,
        classification_confidence=0.95,
    )


def r(update: dict) -> str:
    return route(_clean_w1().model_copy(update=update), CFG).rule_id


# ── one positive case per rule ───────────────────────────────────────────────
def test_r00_watchlist() -> None:
    d = route(_clean_w1().model_copy(update={"watchlist_hit": True}), CFG)
    assert (d.workflow, d.rule_id) == (Workflow.W3, "R-00")


def test_r00_duplicate_hard_match() -> None:
    assert r({"duplicate_hard_match": True}) == "R-00"


def test_r01_incomplete() -> None:
    d = route(_clean_w1().model_copy(update={"completeness": 0.7}), CFG)
    assert (d.workflow, d.rule_id) == (Workflow.W4, "R-01")


def test_r01_low_field_conf() -> None:
    assert r({"min_field_confidence": 0.5}) == "R-01"


def test_r02_lapsed() -> None:
    d = route(_clean_w1().model_copy(update={"policy_active": False, "coverage_covered": False}), CFG)
    assert (d.workflow, d.rule_id) == (Workflow.W2, "R-02")


def test_r02_clear_exclusion() -> None:
    assert r({"clear_exclusion": True, "exclusion_confidence": 0.95, "coverage_covered": False}) == "R-02"


def test_r03_clean_glass() -> None:
    d = route(_clean_w1(), CFG)
    assert (d.workflow, d.rule_id) == (Workflow.W1, "R-03")


def test_r04_high_fraud() -> None:
    d = route(_clean_w1().model_copy(update={"fraud_score": 0.81}), CFG)
    assert (d.workflow, d.rule_id) == (Workflow.W3, "R-04")


def test_r05_high_severity() -> None:
    d = route(_clean_w1().model_copy(update={"severity": 4}), CFG)
    assert (d.workflow, d.rule_id) == (Workflow.W5, "R-05")


def test_r05_injury() -> None:
    assert r({"injury_flag": True}) == "R-05"


def test_r05_large_amount() -> None:
    assert r({"amount_est": 30000}) == "R-05"


def test_r05_attorney() -> None:
    assert r({"attorney_flag": True}) == "R-05"


def test_r05_weak_coverage_confidence() -> None:
    # covered but coverage confidence below the low floor → escalate
    assert r({"coverage_confidence": 0.5, "amount_est": 1000}) == "R-05"


def test_r06_ambiguous_fraud_band_flags_tiebreak() -> None:
    d = route(_clean_w1().model_copy(update={"fraud_score": 0.5}), CFG)
    assert d.rule_id == "R-06"
    assert d.workflow is Workflow.W2  # conservative default
    assert d.needs_tiebreak is True


def test_r99_default() -> None:
    # covered, cheap-ish but above ceiling, no other rule → default W2
    d = route(_clean_w1().model_copy(update={"amount_est": 9000}), CFG)
    assert (d.workflow, d.rule_id) == (Workflow.W2, "R-99")


# ── precedence / order ───────────────────────────────────────────────────────
def test_r00_beats_everything() -> None:
    # incomplete + watchlist: R-00 (fraud) wins over R-01
    assert r({"watchlist_hit": True, "completeness": 0.3}) == "R-00"


def test_r01_beats_r02() -> None:
    assert r({"completeness": 0.5, "policy_active": False}) == "R-01"


def test_r02_beats_r03() -> None:
    assert r({"policy_active": False}) == "R-02"


def test_r04_beats_r05() -> None:
    # fraud high AND high severity → R-04 (checked first)
    assert r({"fraud_score": 0.8, "severity": 5}) == "R-04"


# ── config-driven ────────────────────────────────────────────────────────────
def test_ceiling_is_config_driven() -> None:
    inp = _clean_w1().model_copy(update={"amount_est": 9000})
    assert route(inp, CFG).rule_id == "R-99"
    assert route(inp, RoutingConfig(auto_pay_ceiling=10000)).rule_id == "R-03"


def test_fraud_thresholds_config_driven() -> None:
    inp = _clean_w1().model_copy(update={"fraud_score": 0.5})
    assert route(inp, CFG).rule_id == "R-06"
    # lower the high threshold so 0.5 now counts as outright fraud
    assert route(inp, RoutingConfig(fraud_high=0.4)).rule_id == "R-04"


@pytest.mark.parametrize("severity", [1, 2])
def test_low_severity_can_stp(severity: int) -> None:
    assert r({"severity": severity}) == "R-03"


@pytest.mark.parametrize("severity", [4, 5])
def test_high_severity_escalates(severity: int) -> None:
    assert r({"severity": severity}) == "R-05"
