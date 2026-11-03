import asyncio

from uuid import uuid4

from app.mcp_client.traced_tools import extract_tool_data, traced_mcp_client

async def main() -> None:

    async with traced_mcp_client(
        run_id=f"mcp-smoke-{uuid4()}",
        agent_id="smoke_test",
        node_id="read_resource",
    ) as client:

        tools = await client.list_tools()

        print("\nAvailable MCP tools:")

        for tool in tools:
            print(f"- {tool.name}")

        expected_tools = {
            "read_shared_resource",
            "write_shared_resource",
            "naive_write_shared_resource",
            "acquire_resource_lock",
            "release_resource_lock",
            "locked_write_shared_resource",
            "list_shared_resources",
        }
        missing = expected_tools - {tool.name for tool in tools}
        assert not missing, f"Missing MCP tools: {sorted(missing)}"

        print("\nReading resource...")

        result = await client.call_tool(
            "read_shared_resource",
            {
                "resource_key":
                    "inventory/product_1"
            },
        )

        print("\nRead result:")
        data = extract_tool_data(result)
        print(data)
        assert data.get("status") == "ok", data
        assert data.get("resource_key") == "inventory/product_1", data
        assert "value" in data and "version" in data, data


if __name__ == "__main__":
    asyncio.run(main())
