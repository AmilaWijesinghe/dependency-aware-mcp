from typing import Literal

from pydantic import BaseModel, Field


class SemanticConflictDecision(BaseModel):
    """
    Structured output produced by the Semantic Auditor.
    """

    semantic_result: Literal[
        "disruptive",
        "non_disruptive",
    ] = Field(
        description=(
            "Whether the external state change invalidates "
            "a premise required by the worker's intended task."
        )
    )

    affected_premises: list[str] = Field(
        default_factory=list,
        description=(
            "Specific assumptions or premises invalidated " "by the new resource state."
        ),
    )

    reason: str = Field(
        description=(
            "Short explanation grounded in the old state, "
            "new state, and worker purpose."
        )
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=("Confidence in this semantic classification."),
    )
