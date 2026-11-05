"""Inspect the installed MCP client's raw read response and validate extraction."""

import asyncio
from uuid import uuid4

from app.mcp_client.traced_tools import extract_tool_data, traced_mcp_client


async def main() -> None:
    async with traced_mcp_client(
        run_id=str(uuid4()),
        agent_id="debug_agent",
        node_id="debug_read",
    ) as client:
        result = await client.call_tool(
            "read_shared_resource",
            {"resource_key": "inventory/product_1"},
        )

    print("\nRAW MCP RESULT")
    for field in ("data", "structured_content", "content"):
        print(f"{field}:", getattr(result, field, None))

    data = extract_tool_data(result)
    print("\nEXTRACTED RESULT")
    print(data)

    assert data.get("status") == "ok", data
    assert data.get("resource_key") == "inventory/product_1", data
    assert "value" in data, data
    assert "version" in data, data


if __name__ == "__main__":
    asyncio.run(main())
