import asyncio

from mcp import Client


MCP_URL = "http://127.0.0.1:8001/mcp"


async def main() -> None:

    async with Client(MCP_URL) as client:

        tools = await client.list_tools()

        print("\nAvailable MCP tools:")

        for tool in tools.tools:
            print(f"- {tool.name}")

        print("\nReading resource...")

        result = await client.call_tool(
            "read_shared_resource",
            {
                "resource_key":
                    "inventory/product_1"
            },
        )

        print("\nRead result:")
        print(result)


if __name__ == "__main__":
    asyncio.run(main())