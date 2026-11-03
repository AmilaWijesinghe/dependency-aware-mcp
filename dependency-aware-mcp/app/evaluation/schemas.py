from dataclasses import asdict, dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

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

    def to_dict(self) -> dict:
        return asdict(self)


class WorkerPreparation(BaseModel):

    task_summary: str

    required_fields: list[str]

    reasoning_plan: list[str]


class WorkerDecision(BaseModel):

    action: Literal[
        "write",
        "stop",
    ]

    new_value: dict[str, Any] | None = None

    reason: str

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )
