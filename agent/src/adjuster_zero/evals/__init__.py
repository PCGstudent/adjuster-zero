"""Eval harness: a labeled golden claim set replayed through the real graph, with
a route confusion matrix + pass rate. The eval gate guards prompt/rule changes."""

from .golden import GoldenClaim, golden_claims

__all__ = ["GoldenClaim", "golden_claims"]
