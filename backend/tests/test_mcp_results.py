"""Response compatibility tests without MongoDB, HTTP servers, or model calls."""

import unittest
from types import SimpleNamespace

from fastmcp import Client
from fastmcp.client.client import CallToolResult
from mcp.server import MCPServer
from mcp.types import TextContent

from app.mcp_client.results import tool_result_dict
from app.mcp_client.traced_tools import extract_tool_data


class MCPResultTests(unittest.IsolatedAsyncioTestCase):
    def test_compatibility_name_uses_the_shared_extractor(self):
        self.assertIs(tool_result_dict, extract_tool_data)

    async def test_sdk_server_dict_response(self):
        server = MCPServer("response-test")
        payload = {"status": "ok", "value": {"quantity": 60, "price": 25}, "version": 3}

        @server.tool()
        def write_example() -> dict:
            return payload

        async with Client(server) as client:
            result = await client.call_tool("write_example", {})

        self.assertEqual(tool_result_dict(result), payload)

    def test_structured_and_decoded_responses(self):
        payload = {"status": "ok", "version": 3}
        for fields in ({"data": payload}, {"structured_content": payload}):
            with self.subTest(fields=fields):
                result = CallToolResult(
                    content=[], meta=None, is_error=False,
                    **{"structured_content": None, **fields},
                )
                self.assertEqual(tool_result_dict(result), payload)

    def test_conflict_remains_a_conflict(self):
        result = CallToolResult(
            structured_content=None, meta=None,
            content=[TextContent(type="text", text='{"status":"conflict"}')],
            is_error=False,
        )
        self.assertEqual(tool_result_dict(result), {"status": "conflict"})

    def test_precedence_and_result_wrappers(self):
        payload = {"status": "ok", "version": 3}
        for result in (
            SimpleNamespace(data=payload, structured_content={"wrong": True}),
            SimpleNamespace(structured_content={"result": payload}),
            SimpleNamespace(content=[TextContent(type="text", text='{"result":{"status":"ok","version":3}}')]),
        ):
            with self.subTest(result=result):
                self.assertEqual(extract_tool_data(result), payload)

    def test_json_dictionary_after_other_text_blocks(self):
        result = SimpleNamespace(content=[
            TextContent(type="text", text="Read result follows"),
            TextContent(type="text", text="[]"),
            TextContent(type="text", text='{"status":"ok"}'),
        ])
        self.assertEqual(extract_tool_data(result), {"status": "ok"})

    def test_missing_result_includes_diagnostic_fields(self):
        with self.assertRaisesRegex(
            RuntimeError, "no usable dictionary.*data=None.*structured_content=None.*content=",
        ):
            extract_tool_data(None)

    def test_tool_error_is_rejected_even_with_object_data(self):
        result = CallToolResult(
            structured_content=None, meta=None,
            content=[TextContent(type="text", text="Write failed")],
            data={"status": "ok"},
            is_error=True,
        )
        with self.assertRaisesRegex(RuntimeError, "MCP tool failed: Write failed"):
            tool_result_dict(result)

    def test_invalid_or_ambiguous_content_is_rejected(self):
        for texts in ([], ["invalid json"], ["[]"], ['{"status":"ok"}', '{}']):
            with self.subTest(texts=texts):
                result = CallToolResult(
                    structured_content=None, meta=None,
                    content=[TextContent(type="text", text=text) for text in texts],
                    is_error=False,
                )
                with self.assertRaises(RuntimeError):
                    tool_result_dict(result)


if __name__ == "__main__":
    unittest.main()
