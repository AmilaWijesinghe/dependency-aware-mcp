from typing import TypedDict


class Phase1State(
    TypedDict,
    total=False,
):
    run_id: str

    resource_key: str

    initial_version: int
    initial_quantity: int
    initial_price: int
    initial_description: str

    worker_a_read: str
    worker_b_read: str

    worker_b_write: str
    worker_a_stale_write: str

    verification: str


class Phase3State(
    TypedDict,
    total=False,
):
    run_id: str

    scenario_name: str

    semantic_ground_truth: str

    resource_key: str

    initial_version: int

    initial_value: dict

    b_write_value: dict

    a_stale_write_value: dict

    a_task_purpose: str

    worker_a_read: str
    worker_b_read: str

    worker_b_write: str
    worker_a_stale_write: str

    audit_decision: dict

    verification: str


class Phase4State(
    TypedDict,
    total=False,
):
    run_id: str

    scenario_name: str

    semantic_ground_truth: str

    resource_key: str

    initial_version: int

    initial_value: dict

    b_write_value: dict

    a_stale_write_value: dict

    a_task_purpose: str

    worker_a_read: str
    worker_b_read: str

    worker_b_write: str
    worker_a_stale_write: str

    audit_decision: dict

    affected_nodes: list[str]

    preserved_nodes: list[str]

    recovery_strategy: str

    recovery_current_value: dict

    recovery_current_version: int

    recovery_decision: dict

    recovery_result: dict

    verification: str
