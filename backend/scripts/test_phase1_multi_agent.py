import asyncio
import logging

from langchain.mcp import MCPAdapter

from app.agents.workers import create_worker_agents
from app.config import settings
from app.graph.phase1 import build_phase1_graph
from app.storage.mongodb import (
    close_database,
    ping_database,
    resources,
)

logging.basicConfig(
    level=logging.INFO,
    format=("%(asctime)s | " "%(levelname)s | " "%(name)s | " "%(message)s"),
)

logger = logging.getLogger(__name__)


async def verify_database() -> None:
    """
    Verify final MongoDB state directly.

    This direct database access belongs only to the test harness,
    not to the agents.
    """

    resource = await resources.find_one({"_id": "inventory/product_1"})

    print("\n================================")
    print("DIRECT MONGODB VERIFICATION")
    print("================================")

    print(resource)

    if resource is None:
        raise AssertionError("Test resource does not exist.")

    assert resource["version"] == 2, (
        f"Expected version 2, " f'got {resource["version"]}'
    )

    assert (
        resource["value"]["quantity"] == 60
    ), "Worker B's quantity update was not preserved."

    assert (
        resource["value"]["price"] == 20
    ), "Worker A's stale price write should have been rejected."

    print("\nPASS:")
    print("MongoDB final version = 2")
    print("MongoDB final quantity = 60")
    print("MongoDB final price = 20")
    print("Worker A's stale write did not overwrite Worker B.")


async def main() -> None:
    # ---------------------------------------------------------
    # 1. Verify database connectivity
    # ---------------------------------------------------------

    await ping_database()

    print("\nMongoDB connected.")

    # ---------------------------------------------------------
    # 2. Connect to MCP
    # ---------------------------------------------------------

    async with MCPAdapter(settings.mcp_url) as adapter:

        tools = await adapter.list_tools()

        print("\n================================")
        print("MCP TOOLS")
        print("================================")

        for tool in tools:
            print(f"- {tool.name}")

        # -----------------------------------------------------
        # 3. Create independent Deep Agents
        # -----------------------------------------------------

        worker_a, worker_b = create_worker_agents(tools)

        # -----------------------------------------------------
        # 4. Build Phase 1 LangGraph
        # -----------------------------------------------------

        graph = build_phase1_graph(
            worker_a,
            worker_b,
        )

        # -----------------------------------------------------
        # 5. Initial benchmark snapshot
        # -----------------------------------------------------

        initial_state = {
            "resource_key": "inventory/product_1",
            "initial_version": 1,
            "initial_quantity": 100,
            "initial_price": 20,
            "initial_description": "Test Product",
        }

        print("\n================================")
        print("STARTING PHASE 1")
        print("================================")

        # -----------------------------------------------------
        # 6. Execute graph
        # -----------------------------------------------------

        result = await graph.ainvoke(initial_state)

        # -----------------------------------------------------
        # 7. Show results
        # -----------------------------------------------------

        print("\n================================")
        print("WORKER A INITIAL READ")
        print("================================")

        print(
            result.get(
                "worker_a_read",
                "No output",
            )
        )

        print("\n================================")
        print("WORKER B INITIAL READ")
        print("================================")

        print(
            result.get(
                "worker_b_read",
                "No output",
            )
        )

        print("\n================================")
        print("WORKER B WRITE")
        print("================================")

        print(
            result.get(
                "worker_b_write",
                "No output",
            )
        )

        print("\n================================")
        print("WORKER A STALE WRITE")
        print("================================")

        stale_result = result.get(
            "worker_a_stale_write",
            "",
        )

        print(stale_result)

        print("\n================================")
        print("FINAL MCP VERIFICATION")
        print("================================")

        print(
            result.get(
                "verification",
                "No output",
            )
        )

        if "conflict" not in stale_result.lower():
            print(
                "\nWARNING: Worker A's final message "
                "did not explicitly contain the word "
                "'conflict'. Check the MCP server logs."
            )

    # ---------------------------------------------------------
    # 8. Verify actual database state
    # ---------------------------------------------------------

    await verify_database()

    await close_database()


if __name__ == "__main__":
    asyncio.run(main())
