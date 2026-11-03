"""Trace propagation through real MCP HTTP messages, without MongoDB or Ollama.

Run independently of the legacy SQLite fixtures:
    python -m unittest discover -s tests -p test_research_trace.py
"""

import asyncio
import unittest
from functools import wraps
from unittest.mock import AsyncMock, patch

import httpx2
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from app.mcp_client import traced_tools
from app.mcp_client.results import tool_result_dict
from app.mcp_server.server import mcp


def with_server_lifespan(test):
    @wraps(test)
    async def run(self):
        async with self.app.router.lifespan_context(self.app):
            await test(self)
    return run


class ResearchTraceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = mcp.streamable_http_app(stateless_http=True, json_response=True)
        self.resources = AsyncMock()
        self.resources.find_one.return_value = {
            "_id": "inventory/product_1", "value": {"quantity": 100}, "version": 1,
        }
        self.provenance = AsyncMock()
        for name, value in (
            ("app.concurrency.middleware.resources", self.resources),
            ("app.mcp_server.server.middleware.provenance", self.provenance),
        ):
            patcher = patch(name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        # Keep the production transport and HTTP stack; route requests to ASGI
        # in process so the test needs neither a port nor a running server.
        def transport_factory(*args, **kwargs):
            return StreamableHttpTransport(
                *args, **kwargs,
                httpx_client_factory=lambda **options: httpx2.AsyncClient(
                    **options, transport=httpx2.ASGITransport(app=self.app),
                ),
            )

        self.transport_factory = transport_factory
        patcher = patch.object(traced_tools, "StreamableHttpTransport", transport_factory)
        patcher.start()
        self.addCleanup(patcher.stop)

    @with_server_lifespan
    async def test_traced_clients_keep_concurrent_identities_separate(self):
        async def read(agent_id):
            async with traced_tools.traced_mcp_client(
                run_id="run-test", agent_id=agent_id, node_id="read",
            ) as client:
                result = await client.call_tool(
                    "read_shared_resource", {"resource_key": "inventory/product_1"},
                )
                self.assertEqual(tool_result_dict(result)["status"], "ok")

        await asyncio.gather(read("worker_a"), read("worker_b"))
        calls = self.provenance.record_read.await_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual({call.kwargs["agent_id"] for call in calls}, {"worker_a", "worker_b"})
        for call in calls:
            self.assertEqual(call.kwargs["run_id"], "run-test")
            self.assertEqual(call.kwargs["node_id"], "read")

    @with_server_lifespan
    async def test_langchain_adapter_sends_trace_headers(self):
        async with traced_tools.traced_mcp_tools(
            run_id="run-llm", agent_id="worker_llm", node_id="reason",
        ) as tools:
            read = next(tool for tool in tools if tool.name == "read_shared_resource")
            await read.ainvoke({"resource_key": "inventory/product_1"})

        call = self.provenance.record_read.await_args
        self.assertEqual(call.kwargs["run_id"], "run-llm")
        self.assertEqual(call.kwargs["agent_id"], "worker_llm")
        self.assertEqual(call.kwargs["node_id"], "reason")

    @with_server_lifespan
    async def test_missing_headers_return_actionable_error_before_database_access(self):
        for headers, missing in (
            ({}, "X-Research-Run-Id, X-Research-Agent-Id, X-Research-Node-Id"),
            ({"x-research-run-id": "run-test"}, "X-Research-Agent-Id, X-Research-Node-Id"),
        ):
            with self.subTest(headers=headers):
                transport = self.transport_factory(traced_tools.settings.mcp_url, headers=headers)
                async with Client(transport) as client:
                    result = await client.call_tool(
                        "read_shared_resource", {"resource_key": "inventory/product_1"},
                        raise_on_error=False,
                    )
                self.assertTrue(result.is_error)
                self.assertIn(
                    "Missing research trace headers: " + missing,
                    "\n".join(block.text for block in result.content if block.type == "text"),
                )
        self.resources.find_one.assert_not_awaited()
        self.provenance.record_read.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
