import asyncio

from deepagents import create_deep_agent
from langchain.mcp import MCPAdapter
from langchain_ollama import ChatOllama

from app.config import settings

MCP_URL = "http://127.0.0.1:8001/mcp"


async def main() -> None:

    # -----------------------------------------
    # 1. Create local Ollama chat model
    # -----------------------------------------

    model = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0,
    )

    # -----------------------------------------
    # 2. Connect LangChain to MCP
    # -----------------------------------------

    async with MCPAdapter(MCP_URL) as adapter:

        tools = await adapter.list_tools()

        print("\nMCP tools available to the agent:")

        for tool in tools:
            print(f"- {tool.name}")

        # -------------------------------------
        # 3. Create Deep Agent
        # -------------------------------------

        agent = create_deep_agent(
            model=model,
            tools=tools,
            system_prompt="""
You are testing a version-controlled shared resource
system.

You must use the supplied MCP tools to interact with
shared resources.

Rules:

1. Always read a resource before modifying it.

2. Never assume or invent the current value.

3. Never assume or invent a resource version.

4. Remember the version returned by
   read_shared_resource.

5. When calling write_shared_resource, pass the
   exact version returned by your read as
   expected_version.

6. Preserve all fields the user did not ask you to
   modify.

7. After successfully writing a resource, read it
   again to verify the final state.

8. Report the final value and final version only
   after verification.
""",
        )

        # -------------------------------------
        # 4. Give the agent our test task
        # -------------------------------------

        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": """
Read the shared resource:

inventory/product_1

Change ONLY its quantity to 180.

Do not change:
- price
- description

Use the resource version returned by the read as
expected_version when writing.

After writing, read the resource again.

Tell me the final quantity, price, description,
and version.
""",
                    }
                ]
            }
        )

        # -------------------------------------
        # 5. Print final answer
        # -------------------------------------

        print("\n============================")
        print("FINAL AGENT RESPONSE")
        print("============================")

        final_message = result["messages"][-1]

        print(final_message.content)


if __name__ == "__main__":
    asyncio.run(main())
