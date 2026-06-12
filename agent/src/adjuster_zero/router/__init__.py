"""Deterministic routing (thesis 2). A pure function over typed inputs reads
thresholds from versioned config. The LLM never routes (except the R-06
tiebreak band, added in Phase 2)."""

from .rules import RouterInput, RoutingConfig, RoutingDecision, route

__all__ = ["RouterInput", "RoutingConfig", "RoutingDecision", "route"]
