"""Toy schemas for the Phase 0 /debug/llm-echo pipeline proof.

Real claim schemas live in Phase 1+. This 3-field model just exercises the
structured-output + validation + RPD-counter path end to end.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Sentiment(StrEnum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"


class ToyClassification(BaseModel):
    sentiment: Sentiment = Field(description="Overall sentiment of the sentence.")
    topic: str = Field(description="A 1-3 word topic label.")
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence 0..1.")
