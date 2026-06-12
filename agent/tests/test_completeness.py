"""Deterministic intake completeness (thesis 1/2).

Completeness is a pure projection of the required intake facts — policy_number,
loss_date, loss_location — never the LLM's self-reported `overall_completeness`.
These tests pin that contract so a fully-specified claim can't be sent to the
information-request loop by an LLM that under-scores itself.
"""

from __future__ import annotations

from adjuster_zero.planner import REQUIRED_INTAKE_FIELDS, assess_completeness


def test_all_required_present_is_complete() -> None:
    fields = {
        "policy_number": "POL-88341",
        "loss_date": "2026-06-08",
        "loss_location": "I-80 near Sacramento",
        "peril": "glass",          # not required for completeness
        "description": "cracked windshield",
    }
    completeness, missing = assess_completeness(fields)
    assert completeness == 1.0
    assert missing == []


def test_missing_date_and_location_is_incomplete() -> None:
    # A photo gives the damage (peril/description) but not when/where.
    completeness, missing = assess_completeness(
        {"policy_number": "POL-88341", "peril": "glass", "description": "dented door"})
    assert completeness < 0.9  # → R-01 → W4
    assert set(missing) == {"loss_date", "loss_location"}


def test_supplying_date_and_location_lifts_to_complete() -> None:
    # The exact fix for the photo-intake report: add date + location → complete.
    base = {"policy_number": "POL-88341", "peril": "glass"}
    assert assess_completeness(base)[0] < 0.9
    base.update({"loss_date": "2026-06-08", "loss_location": "I-80 near Sacramento"})
    assert assess_completeness(base)[0] == 1.0


def test_blank_values_do_not_count_as_present() -> None:
    completeness, missing = assess_completeness(
        {"policy_number": "POL-1", "loss_date": "   ", "loss_location": None})
    assert completeness < 0.9
    assert set(missing) == {"loss_date", "loss_location"}


def test_peril_and_description_never_gate_completeness() -> None:
    # Even with a rich narrative + peril, missing the intake facts is incomplete.
    completeness, _ = assess_completeness(
        {"peril": "collision", "description": "rear-ended at a light, airbag deployed"})
    assert completeness == 0.0
    assert "peril" not in REQUIRED_INTAKE_FIELDS
    assert "description" not in REQUIRED_INTAKE_FIELDS
