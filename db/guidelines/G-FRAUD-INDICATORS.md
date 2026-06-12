# G-FRAUD-INDICATORS — Fraud Screening Indicators

## Common indicators
Near-duplicate loss narratives across claims, a recent coverage increase shortly
before the loss, a cluster of claims in a short window, an uncorroborated weather
peril, and inconsistent loss dates are fraud-screening signals.

## Scoring
Signals are weighted and summed into a 0–1 fraud score. A score above the high
threshold, or any hard signal (watchlist hit, exact duplicate), routes the claim
to the SIU fraud workflow — from which no payment path is reachable.

## Degraded controls
If a fraud control (duplicate index, weather verification) is unavailable, the
claim must not be straight-through processed; routing is capped at standard
adjudication until the control is restored.
