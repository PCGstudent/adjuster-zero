"""Synthetic data: policies, claimants, and parameterized FNOL scenarios with
ground-truth labels (for the demo and the Phase 4 eval golden set). 100%
synthetic — never real PII."""

from .data import CLAIMANTS, POLICIES, SCENARIOS, Scenario, get_scenario

__all__ = ["CLAIMANTS", "POLICIES", "SCENARIOS", "Scenario", "get_scenario"]
