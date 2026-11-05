from dataclasses import (
    asdict,
    dataclass,
)
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

ProtocolName = Literal[
    "naive",
    "2pl",
    "occ",
    "dependency_occ",
]


@dataclass
class OperationSpec:
    operation: Literal[
        "set",
        "subtract",
    ]

    field: str

    value: Any | None = None

    amount: int | float | None = None


@dataclass
class BenchmarkScenario:
    scenario_id: str

    name: str

    semantic_ground_truth: Literal[
        "disruptive",
        "non_disruptive",
    ]

    initial_value: dict

    worker_a_task: str

    worker_b_task: str

    worker_a_operation: OperationSpec

    worker_b_operation: OperationSpec

    expected_final: dict


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def __add__(
        self,
        other: "TokenUsage",
    ) -> "TokenUsage":

        return TokenUsage(
            input_tokens=(self.input_tokens + other.input_tokens),
            output_tokens=(self.output_tokens + other.output_tokens),
            total_tokens=(self.total_tokens + other.total_tokens),
        )


@dataclass
class BenchmarkResult:
    benchmark_id: str

    run_id: str

    repetition: int

    protocol: str

    scenario_id: str

    correct: bool

    elapsed_ms: float

    input_tokens: int = 0

    output_tokens: int = 0

    total_tokens: int = 0

    wasted_tokens: int = 0

    conflicts: int = 0

    retries: int = 0

    lock_wait_ms: float = 0.0

    nodes_reexecuted: int = 0

    nodes_preserved: int = 0

    semantic_prediction: str | None = None

    semantic_ground_truth: str | None = None

    final_value: dict | None = None

    final_version: int | None = None

    error: str | None = None

    resource_key: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class WorkerPreparation(BaseModel):

    model_config = ConfigDict(extra="forbid")

    task_summary: str

    required_fields: list[str]

    reasoning_plan: list[str]


class ResourceState(BaseModel):
    """
    Exact shared-resource schema used by the benchmark.

    This prevents workers from inventing fields such as
    `product_description`.
    """

    model_config = ConfigDict(extra="forbid")

    quantity: int

    price: int | float

    description: str


class WorkerDecision(BaseModel):
    """
    Structured worker decision.

    For action='write':
        new_value must contain the COMPLETE resource.

    For action='stop':
        new_value is normalized to None.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "write",
        "stop",
    ]

    # Keep this as a dict so existing benchmark code does
    # not need to change.
    new_value: dict[str, Any] | None = None

    # Defaults make STOP responses easier for local models
    # to satisfy without producing parsing failures.
    reason: str = ""

    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "WorkerDecision":

        # ---------------------------------------------
        # STOP
        #
        # A model may produce null, {}, or omit the
        # value. All mean the same thing here.
        # ---------------------------------------------

        if self.action == "stop":

            self.new_value = None

            return self

        # ---------------------------------------------
        # WRITE
        # ---------------------------------------------

        if self.new_value is None:

            raise ValueError("action='write' requires new_value")

        # Validate exact benchmark resource fields.
        validated = ResourceState.model_validate(self.new_value)

        # Keep downstream API as dict.
        self.new_value = validated.model_dump()

        return self
