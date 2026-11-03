import asyncio
import json
from datetime import (
    datetime,
    timezone,
)
from pprint import pprint
from uuid import uuid4

from app.graph.phase4 import (
    build_phase4_graph,
)
from app.storage.mongodb import (
    close_database,
    conflicts,
    ensure_indexes,
    node_executions,
    ping_database,
    resources,
)

RESOURCE_KEY = "inventory/product_1"


INITIAL_VALUE = {
    "quantity": 100,
    "price": 20,
    "description": "Test Product",
}


SCENARIOS = [
    {
        "name": "benign_price_rebase",
        "ground_truth": "non_disruptive",
        "a_task_purpose": (
            "Change only the product price "
            "from 20 to 25. "
            "This operation does not depend "
            "on available quantity."
        ),
        "a_stale_write_value": {
            "quantity": 100,
            "price": 25,
            "description": "Test Product",
        },
        "b_write_value": {
            "quantity": 60,
            "price": 20,
            "description": "Test Product",
        },
        "expected_final": {
            "quantity": 60,
            "price": 25,
            "description": "Test Product",
        },
        "expected_version": 3,
        "expected_strategy": "rebase",
    },
    {
        "name": "disruptive_allocate_30",
        "ground_truth": "disruptive",
        "a_task_purpose": (
            "Allocate exactly 30 units of "
            "this product from inventory. "
            "Allocation means subtract 30 "
            "from the CURRENT available "
            "quantity. Preserve price and "
            "description. If fewer than "
            "30 units are available, stop "
            "without writing."
        ),
        # Based on OLD quantity=100:
        # 100 - 30 = 70.
        "a_stale_write_value": {
            "quantity": 70,
            "price": 20,
            "description": "Test Product",
        },
        # Worker B changes inventory first.
        "b_write_value": {
            "quantity": 60,
            "price": 20,
            "description": "Test Product",
        },
        # Recovery should use CURRENT=60:
        # 60 - 30 = 30.
        "expected_final": {
            "quantity": 30,
            "price": 20,
            "description": "Test Product",
        },
        "expected_version": 3,
        "expected_strategy": "selective_rerun",
    },
]


async def reset_resource() -> None:

    now = datetime.now(timezone.utc)

    await resources.replace_one(
        {"_id": RESOURCE_KEY},
        {
            "_id": RESOURCE_KEY,
            "value": INITIAL_VALUE.copy(),
            "version": 1,
            "createdAt": now,
            "updatedAt": now,
        },
        upsert=True,
    )


async def run_scenario(
    scenario: dict,
) -> bool:

    await reset_resource()

    run_id = str(uuid4())

    print("\n\n========================================")
    print("PHASE 4 SCENARIO")
    print("========================================")

    print(scenario["name"])

    print(
        "run_id =",
        run_id,
    )

    graph = build_phase4_graph()

    state = {
        "run_id": run_id,
        "scenario_name": scenario["name"],
        "semantic_ground_truth": scenario["ground_truth"],
        "resource_key": RESOURCE_KEY,
        "initial_version": 1,
        "initial_value": INITIAL_VALUE.copy(),
        "b_write_value": scenario["b_write_value"],
        "a_stale_write_value": scenario["a_stale_write_value"],
        "a_task_purpose": scenario["a_task_purpose"],
    }

    result = await graph.ainvoke(
        state,
        config={"configurable": {"thread_id": run_id}},
    )

    print("\n----------------------------------------")
    print("SEMANTIC AUDIT")
    print("----------------------------------------")

    pprint(result["audit_decision"])

    print("\n----------------------------------------")
    print("AFFECTED NODES")
    print("----------------------------------------")

    pprint(result["affected_nodes"])

    print("\nPreserved nodes:")

    pprint(result["preserved_nodes"])

    print(
        "\nRecovery strategy:",
        result["recovery_strategy"],
    )

    print("\nRecovery result:")

    pprint(result["recovery_result"])

    # ---------------------------------------------
    # Actual database result
    # ---------------------------------------------

    resource = await resources.find_one({"_id": RESOURCE_KEY})

    assert resource is not None

    print("\n----------------------------------------")
    print("FINAL RESOURCE")
    print("----------------------------------------")

    pprint(resource)

    predicted = result["audit_decision"]["semantic_result"]

    classification_correct = predicted == scenario["ground_truth"]

    if not classification_correct:

        print("\nAUDITOR CLASSIFICATION ERROR")

        print(
            "Expected:",
            scenario["ground_truth"],
        )

        print(
            "Predicted:",
            predicted,
        )

        print(
            "\nInfrastructure may still be "
            "working correctly, but the "
            "Auditor chose the wrong "
            "recovery path."
        )

        return False

    # ---------------------------------------------
    # Strategy should match ground truth.
    # ---------------------------------------------

    assert result["recovery_strategy"] == scenario["expected_strategy"]

    # ---------------------------------------------
    # Final state check.
    # ---------------------------------------------

    assert resource["value"] == scenario["expected_final"], (
        f"Expected final value "
        f'{scenario["expected_final"]}, '
        f'got {resource["value"]}'
    )

    assert resource["version"] == scenario["expected_version"]

    # ---------------------------------------------
    # Verify B was NOT rerun.
    # ---------------------------------------------

    b_write_count = await node_executions.count_documents(
        {
            "runId": run_id,
            "agentId": "worker_b",
            "nodeId": "b_write",
        }
    )

    assert b_write_count == 1, (
        "Worker B was executed more than once. " "Selective recovery failed."
    )

    # ---------------------------------------------
    # Verify recovery metadata
    # ---------------------------------------------

    conflict = await conflicts.find_one(
        {
            "runId": run_id,
            "agentId": "worker_a",
            "nodeId": "a_stale_write",
        }
    )

    assert conflict is not None

    assert conflict.get("recoveryStrategy") == scenario["expected_strategy"]

    assert conflict.get("recoveryStatus") == "completed"

    print("\n========================================")

    print("PHASE 4 SCENARIO PASS")

    print("========================================")

    print("✓ structural conflict detected")

    print("✓ semantic classification used")

    print("✓ dependency graph evaluated")

    print("✓ affected nodes identified")

    print("✓ Worker B preserved")

    if scenario["expected_strategy"] == "rebase":

        print("✓ benign change rebased " "without re-reasoning")

    else:

        print("✓ Worker A selectively " "re-executed using fresh state")

    print("✓ final MongoDB state correct")

    return True


async def main() -> None:

    await ping_database()

    await ensure_indexes()

    passed = 0

    for scenario in SCENARIOS:

        if await run_scenario(scenario):
            passed += 1

    print("\n\n========================================")

    print("PHASE 4 SUMMARY")

    print("========================================")

    print(f"Passed: " f"{passed}/{len(SCENARIOS)}")

    await close_database()


if __name__ == "__main__":
    asyncio.run(main())
