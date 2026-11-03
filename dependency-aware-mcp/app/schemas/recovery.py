from typing import Any, Literal

from pydantic import BaseModel, Field


class RecoveryDecision(BaseModel):
    """
    Decision produced while selectively re-executing
    an invalidated worker branch.
    """

    action: Literal[
        "write",
        "stop",
    ] = Field(
        description=(
            "write if the task can still be performed "
            "using the current resource state; "
            "stop if it cannot safely proceed."
        )
    )

    new_value: dict[str, Any] | None = Field(
        default=None,
        description=("Complete new resource value when action=write."),
    )

    reason: str = Field(
        description=(
            "Why the operation can or cannot proceed " "using the fresh resource state."
        )
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
