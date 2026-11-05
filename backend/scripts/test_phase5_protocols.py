import asyncio

from pprint import pprint
from uuid import uuid4

from app.graph.phase4 import (
    build_phase4_graph,
)

from app.protocols.baselines import (
    run_2pl,
    run_naive,
    run_occ_full_restart,
)

from app.storage.mongodb import (
    close_database,
    ensure_indexes,
    ping_database,
    resources,
)

from app.evaluation.isolation import execution_resource_key, initialize_resource
from app.evaluation.scenarios import SCENARIOS


INITIAL_VALUE = {
    "quantity": 100,
    "price": 20,
    "description": "Test Product",
}


EXPECTED_VALUE = {
    "quantity": 60,
    "price": 25,
    "description": "Test Product",
}


async def test_naive() -> dict:

    run_id = str(uuid4())
    resource_key = execution_resource_key("phase5", run_id)
    await initialize_resource(resource_key=resource_key, initial_value=INITIAL_VALUE)

    print("\n================================")
    print("NAIVE")
    print("================================")

    result = await run_naive(resource_key=resource_key, run_id=run_id, scenario=SCENARIOS[0])

    pprint(result.as_dict())

    # Naive SHOULD demonstrate lost update.
    assert result.correct is False

    assert result.final_value["quantity"] == 100

    return result.as_dict()


async def test_2pl() -> dict:

    run_id = str(uuid4())
    resource_key = execution_resource_key("phase5", run_id)
    await initialize_resource(resource_key=resource_key, initial_value=INITIAL_VALUE)

    print("\n================================")
    print("APPLICATION-LEVEL 2PL")
    print("================================")

    result = await run_2pl(resource_key=resource_key, run_id=run_id, scenario=SCENARIOS[0])

    pprint(result.as_dict())

    assert result.correct

    assert result.final_value == EXPECTED_VALUE

    assert result.lock_wait_ms > 0

    return result.as_dict()


async def test_occ() -> dict:

    run_id = str(uuid4())
    resource_key = execution_resource_key("phase5", run_id)
    await initialize_resource(resource_key=resource_key, initial_value=INITIAL_VALUE)

    print("\n================================")
    print("FULL-RESTART OCC")
    print("================================")

    result = await run_occ_full_restart(resource_key=resource_key, run_id=run_id, scenario=SCENARIOS[0])

    pprint(result.as_dict())

    assert result.correct

    assert result.final_value == EXPECTED_VALUE

    assert result.conflicts == 1

    assert result.retries == 1

    return result.as_dict()


async def test_dependency_occ() -> dict:

    run_id = str(uuid4())
    resource_key = execution_resource_key("phase5", run_id)
    await initialize_resource(resource_key=resource_key, initial_value=INITIAL_VALUE)

    print("\n================================")
    print("DEPENDENCY-AWARE SEMANTIC OCC")
    print("================================")

    graph = build_phase4_graph()

    state = {
        "run_id": run_id,
        "scenario_name": "phase5_benign_price",
        "semantic_ground_truth": "non_disruptive",
        "resource_key": resource_key,
        "initial_version": 1,
        "initial_value": INITIAL_VALUE.copy(),
        "b_write_value": {
            "quantity": 60,
            "price": 20,
            "description": "Test Product",
        },
        "a_task_purpose": (
            "Change only the product price "
            "from 20 to 25. "
            "The price decision does not "
            "depend on quantity."
        ),
        "a_stale_write_value": {
            "quantity": 100,
            "price": 25,
            "description": "Test Product",
        },
    }

    result = await graph.ainvoke(
        state,
        config={"configurable": {"thread_id": run_id}},
    )

    final_resource = await resources.find_one({"_id": resource_key})

    assert final_resource is not None

    correct = final_resource["value"] == EXPECTED_VALUE

    assert correct

    assert result["recovery_strategy"] == "rebase"

    output = {
        "protocol": "dependency_occ",
        "correct": correct,
        "final_value": final_resource["value"],
        "final_version": final_resource["version"],
        "semantic_result": result["audit_decision"]["semantic_result"],
        "recovery_strategy": result["recovery_strategy"],
        "affected_nodes": result["affected_nodes"],
        "preserved_nodes": result["preserved_nodes"],
    }

    pprint(output)

    return output


async def main() -> None:

    await ping_database()

    await ensure_indexes()

    results = []

    results.append(await test_naive())

    results.append(await test_2pl())

    results.append(await test_occ())

    results.append(await test_dependency_occ())

    print("\n\n================================")
    print("PHASE 5 SUMMARY")
    print("================================")

    for result in results:

        print(f'{result["protocol"]:<25} ' f'correct={result["correct"]}')

    await close_database()


if __name__ == "__main__":
    asyncio.run(main())
