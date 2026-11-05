import asyncio
from datetime import datetime, timezone
from pprint import pprint
from uuid import uuid4

from app.graph.phase3 import (
    build_phase3_graph,
)
from app.storage.mongodb import (
    close_database,
    conflicts,
    ensure_indexes,
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
        "name": "benign_price_change",
        "ground_truth": "non_disruptive",
        "b_write_value": {
            "quantity": 60,
            "price": 20,
            "description": "Test Product",
        },
        "a_task_purpose": (
            "Change only the product price from 20 "
            "to 25. The price change decision does "
            "not depend on available quantity."
        ),
        "a_stale_write_value": {
            "quantity": 100,
            "price": 25,
            "description": "Test Product",
        },
    },
    {
        "name": "disruptive_inventory_allocation",
        "ground_truth": "disruptive",
        "b_write_value": {
            "quantity": 40,
            "price": 20,
            "description": "Test Product",
        },
        "a_task_purpose": (
            "Allocate 50 units of the product. "
            "The earlier snapshot showed 100 units, "
            "so the planned result was 50 units "
            "remaining. This operation requires at "
            "least 50 units to still be available."
        ),
        "a_stale_write_value": {
            "quantity": 50,
            "price": 20,
            "description": "Test Product",
        },
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

    print(f'SCENARIO: {scenario["name"]}')

    print("========================================")

    print(
        "Ground truth:",
        scenario["ground_truth"],
    )

    graph = build_phase3_graph()

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

    result = await graph.ainvoke(state)

    print("\n------------------------------")
    print("AUDITOR DECISION")
    print("------------------------------")

    pprint(result["audit_decision"])

    predicted = result["audit_decision"]["semantic_result"]

    correct = predicted == scenario["ground_truth"]

    print(
        "\nGround truth:",
        scenario["ground_truth"],
    )

    print(
        "Predicted:",
        predicted,
    )

    print(
        "Classification:",
        ("CORRECT" if correct else "INCORRECT"),
    )

    # ---------------------------------------------
    # Verify MongoDB conflict was updated.
    # ---------------------------------------------

    conflict = await conflicts.find_one(
        {
            "runId": run_id,
            "agentId": "worker_a",
            "nodeId": "a_stale_write",
        }
    )

    assert conflict is not None

    assert conflict.get("semanticResult") is not None

    assert conflict.get("semanticReason") is not None

    print("\n------------------------------")
    print("CONFLICT DOCUMENT")
    print("------------------------------")

    pprint(conflict)

    # Structural OCC must still prevent the stale write.
    final_resource = await resources.find_one({"_id": RESOURCE_KEY})

    assert final_resource is not None

    assert final_resource["version"] == 2

    print("\nFinal resource:")

    pprint(final_resource)

    return correct


async def main() -> None:

    await ping_database()

    await ensure_indexes()

    correct_count = 0

    for scenario in SCENARIOS:

        correct = await run_scenario(scenario)

        if correct:
            correct_count += 1

    print("\n\n========================================")

    print("PHASE 3 SUMMARY")

    print("========================================")

    print(f"Correct classifications: " f"{correct_count}/{len(SCENARIOS)}")

    print(
        "NOTE: An incorrect semantic classification "
        "is a model result, not necessarily an "
        "infrastructure failure."
    )

    await close_database()


if __name__ == "__main__":
    asyncio.run(main())
