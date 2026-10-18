"""Schema definitions for ModelAnswer and validation."""
from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field


class ModelPoint(BaseModel):
    """A proposed factual or interpretive point by the model."""
    point_id: str = Field(description="Unique point identifier, e.g. p1")
    kind: str = Field(
        description="Classification: STATED, RESTATEMENT, INTERPRETATION, CONCERN, AMBIGUITY, CONFLICT, GENERAL_EXPLANATION"
    )
    text: str = Field(description="Assistant-authored point text")
    sids: List[str] = Field(default_factory=list, description="List of cited sentence IDs from tools")


class ModelAnswer(BaseModel):
    """Untrusted model response schema (Guide Appendix A2)."""
    points: List[ModelPoint] = Field(default_factory=list, description="List of points proposed by the model")
