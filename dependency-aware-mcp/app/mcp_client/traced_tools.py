import json
from contextlib import asynccontextmanager

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from langchain.mcp import MCPAdapter

from app.config import settings


def extract_tool_data(result) -> dict:
    """Decode a raw MCP object result, preferring data, then structured output.

    MCPServer may return JSON only in TextContent, leaving data as None.
    Reject tool errors and ambiguous text output rather than reporting success.
    """
    content = getattr(result, "content", None) or []
    if getattr(result, "is_error", False):
        detail = "\n".join(
            block.text for block in content if getattr(block, "text", None)
        )
        raise RuntimeError(f"MCP tool failed: {detail or 'unspecified error'}")

    data = getattr(result, "data", None)
    if isinstance(data, dict):
        return data

    def unwrap(data: dict) -> dict:
        if len(data) == 1 and isinstance(data.get("result"), dict):
            return data["result"]
        return data

    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return unwrap(structured)

    dictionaries = []
    for block in content:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            dictionaries.append(unwrap(parsed))

    if len(dictionaries) == 1:
        return dictionaries[0]

    reason = "ambiguous dictionaries" if dictionaries else "no usable dictionary"
    raise RuntimeError(
        f"MCP tool returned {reason}. "
        f"data={data!r}, structured_content={structured!r}, content={content!r}"
    )


def _trace_headers(
    *,
    run_id: str,
    agent_id: str,
    node_id: str,
) -> dict[str, str]:
    """
    Build the HTTP headers used to carry research
    provenance metadata to the MCP server.

    These values are added by the orchestration layer,
    not by the LLM.
    """

    return {
        "X-Research-Run-Id": run_id,
        "X-Research-Agent-Id": agent_id,
        "X-Research-Node-Id": node_id,
    }


@asynccontextmanager
async def traced_mcp_tools(
    *,
    run_id: str,
    agent_id: str,
    node_id: str,
):
    """
    Return MCP tools adapted for LangChain / Deep Agents.

    Use this when an LLM agent needs to call MCP tools.
    """

    transport = StreamableHttpTransport(
        url=settings.mcp_url,
        headers=_trace_headers(
            run_id=run_id,
            agent_id=agent_id,
            node_id=node_id,
        ),
    )

    client = Client(transport=transport)

    async with MCPAdapter(client) as adapter:
        tools = await adapter.list_tools()

        yield tools


@asynccontextmanager
async def traced_mcp_client(
    *,
    run_id: str,
    agent_id: str,
    node_id: str,
):
    """
    Return a raw MCP client for deterministic
    orchestration/recovery operations.

    These operations still go through the MCP server and
    concurrency middleware, so provenance is recorded.
    """

    transport = StreamableHttpTransport(
        url=settings.mcp_url,
        headers=_trace_headers(
            run_id=run_id,
            agent_id=agent_id,
            node_id=node_id,
        ),
    )

    client = Client(transport=transport)

    async with client:
        yield client
