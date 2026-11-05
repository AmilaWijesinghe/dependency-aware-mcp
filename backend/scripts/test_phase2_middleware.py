import asyncio
from pprint import pprint
from uuid import uuid4

from app.graph.phase2 import (
    build_phase2_graph,
)
from app.storage.mongodb import (
    access_logs,
    close_database,
    conflicts,
    dependencies,
    ensure_indexes,
    ping_database,
    resources,
)

RESOURCE_KEY = "inventory/product_1"


async def reset_resource() -> None:

    from datetime import (
        datetime,
        timezone,
    )

    now = datetime.now(timezone.utc)

    await resources.replace_one(
        {"_id": RESOURCE_KEY},
        {
            "_id": RESOURCE_KEY,
            "value": {
                "quantity": 100,
                "price": 20,
                "description": "Test Product",
            },
            "version": 1,
            "createdAt": now,
            "updatedAt": now,
        },
        upsert=True,
    )


async def print_logs(
    run_id: str,
) -> None:

    print("\n================================")
    print("ACCESS LOGS")
    print("================================")

    logs = (
        await access_logs.find({"runId": run_id})
        .sort(
            "timestamp",
            1,
        )
        .to_list(length=100)
    )

    for item in logs:
        pprint(item)

    print("\n================================")
    print("DEPENDENCIES")
    print("================================")

    deps = (
        await dependencies.find({"runId": run_id})
        .sort(
            "timestamp",
            1,
        )
        .to_list(length=100)
    )

    for item in deps:
        pprint(item)

    print("\n================================")
    print("CONFLICTS")
    print("================================")

    conflict_docs = (
        await conflicts.find({"runId": run_id})
        .sort(
            "timestamp",
            1,
        )
        .to_list(length=100)
    )

    for item in conflict_docs:
        pprint(item)


async def validate_phase2(
    run_id: str,
) -> None:

    # -----------------------------------------------------
    # Final resource
    # -----------------------------------------------------

    resource = await resources.find_one({"_id": RESOURCE_KEY})

    assert resource is not None

    assert resource["version"] == 2

    assert resource["value"]["quantity"] == 60

    assert resource["value"]["price"] == 20

    # -----------------------------------------------------
    # Worker A dependency
    # -----------------------------------------------------

    a_dependency = await dependencies.find_one(
        {
            "runId": run_id,
            "agentId": "worker_a",
            "nodeId": "a_read",
            "resourceKey": RESOURCE_KEY,
            "readVersion": 1,
        }
    )

    assert a_dependency is not None

    # -----------------------------------------------------
    # Worker B dependency
    # -----------------------------------------------------

    b_dependency = await dependencies.find_one(
        {
            "runId": run_id,
            "agentId": "worker_b",
            "nodeId": "b_read",
            "resourceKey": RESOURCE_KEY,
            "readVersion": 1,
        }
    )

    assert b_dependency is not None

    # -----------------------------------------------------
    # Worker B successful write
    # -----------------------------------------------------

    b_write = await access_logs.find_one(
        {
            "runId": run_id,
            "agentId": "worker_b",
            "nodeId": "b_write",
            "resourceKey": RESOURCE_KEY,
            "operation": "WRITE",
            "previousVersion": 1,
            "version": 2,
        }
    )

    assert b_write is not None

    # -----------------------------------------------------
    # Worker A stale conflict
    # -----------------------------------------------------

    a_conflict = await conflicts.find_one(
        {
            "runId": run_id,
            "agentId": "worker_a",
            "nodeId": "a_stale_write",
            "resourceKey": RESOURCE_KEY,
            "expectedVersion": 1,
            "actualVersion": 2,
        }
    )

    assert a_conflict is not None

    print("\n================================")
    print("PHASE 2 PASS")
    print("================================")

    print("✓ Worker A read dependency stored")

    print("✓ Worker B read dependency stored")

    print("✓ Worker B write provenance stored")

    print("✓ Worker A conflict stored")

    print("✓ Agent IDs recorded")

    print("✓ LangGraph node IDs recorded")

    print("✓ Run ID correlates all events")

    print("✓ Final MongoDB state correct")


async def main() -> None:

    await ping_database()

    await ensure_indexes()

    await reset_resource()

    run_id = str(uuid4())

    print("\n================================")
    print("PHASE 2 RUN")
    print("================================")

    print(f"run_id = {run_id}")

    graph = build_phase2_graph()

    initial_state = {
        "run_id": run_id,
        "resource_key": RESOURCE_KEY,
        "initial_version": 1,
        "initial_quantity": 100,
        "initial_price": 20,
        "initial_description": "Test Product",
    }

    result = await graph.ainvoke(initial_state)

    print("\n================================")
    print("A READ")
    print("================================")

    print(result.get("worker_a_read"))

    print("\n================================")
    print("B READ")
    print("================================")

    print(result.get("worker_b_read"))

    print("\n================================")
    print("B WRITE")
    print("================================")

    print(result.get("worker_b_write"))

    print("\n================================")
    print("A STALE WRITE")
    print("================================")

    print(result.get("worker_a_stale_write"))

    print("\n================================")
    print("VERIFY")
    print("================================")

    print(result.get("verification"))

    await print_logs(run_id)

    await validate_phase2(run_id)

    await close_database()


if __name__ == "__main__":
    asyncio.run(main())
