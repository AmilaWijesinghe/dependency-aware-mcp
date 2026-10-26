"""FastAPI lifespan and real MCP Streamable HTTP integration."""

import asyncio

from fastapi.testclient import TestClient

from app.config import Settings
from app.concurrency.provenance import ExecutionIdentity
from app.main import create_app
from app.storage import repositories


def test_health_initializes_database_only_in_lifespan(tmp_path):
    path = tmp_path / "data" / "api.db"
    app = create_app(Settings(_env_file=None, database_path=path))
    assert not path.exists()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert app.state.database.path == path
        assert path.exists()


async def test_mcp_contracts_and_stale_write_over_http(mcp_client, database, identity):
    async with mcp_client(identity) as client:
        tools = (await client.list_tools()).tools
        schemas = {tool.name: tool.input_schema for tool in tools}
        assert set(schemas) == {
            "read_shared_resource", "write_shared_resource", "list_shared_resources"
        }
        assert set(schemas["read_shared_resource"]["properties"]) == {"resource_key"}
        assert set(schemas["write_shared_resource"]["properties"]) == {
            "resource_key", "new_value", "expected_version"
        }
        assert schemas["list_shared_resources"]["properties"] == {}
        listing = await client.call_tool("list_shared_resources", {})
        assert listing.structured_content["resources"][0]["version"] == 1
        read = await client.call_tool("read_shared_resource", {"resource_key": "X"})
        assert read.structured_content["value"] == {"quantity": 100}
        updated = await client.call_tool(
            "write_shared_resource",
            {"resource_key": "X", "new_value": {"quantity": 50}, "expected_version": 1},
        )
        assert updated.structured_content["status"] == "ok"
        assert updated.structured_content["version"] == 2
        conflict = await client.call_tool(
            "write_shared_resource",
            {"resource_key": "X", "new_value": {"quantity": 20}, "expected_version": 1},
        )
        assert conflict.structured_content == {
            "status": "conflict", "resource_key": "X",
            "expected_version": 1, "current_version": 2,
        }
    async with database.connect() as connection:
        logs = await repositories.get_access_logs(connection, identity.run_id)
        deps = await repositories.get_dependencies(connection, identity.run_id)
        conflicts = await repositories.get_conflicts(connection, identity.run_id)
        assert (await repositories.get_resource(connection, "X")).value == {"quantity": 50}
    assert [(row["operation"], row["version"]) for row in logs] == [
        ("READ", 1), ("READ", 1), ("WRITE", 2)
    ]
    assert len(deps) == 2
    assert len(conflicts) == 1


async def test_mcp_missing_identity_is_structured_and_cannot_write(mcp_client, database):
    async with mcp_client() as client:
        for name, arguments in [
            ("read_shared_resource", {"resource_key": "X"}),
            ("list_shared_resources", {}),
            ("write_shared_resource", {
                "resource_key": "X", "new_value": {"quantity": 0}, "expected_version": 1
            }),
        ]:
            result = await client.call_tool(name, arguments)
            assert result.structured_content["error"] == "missing_execution_context"
    async with database.connect() as connection:
        assert (await repositories.get_resource(connection, "X")).version == 1
        async with connection.execute("SELECT COUNT(*) FROM access_logs") as cursor:
            assert (await cursor.fetchone())[0] == 0


async def test_mcp_missing_resource_and_bad_version(mcp_client, identity, database):
    async with mcp_client(identity) as client:
        for name, arguments in [
            ("read_shared_resource", {"resource_key": "missing"}),
            ("write_shared_resource", {
                "resource_key": "missing", "new_value": {}, "expected_version": 1
            }),
        ]:
            result = await client.call_tool(name, arguments)
            assert result.structured_content == {
                "status": "error", "error": "resource_not_found", "resource_key": "missing"
            }
        for version in [0, -1, True, "1"]:
            result = await client.call_tool(
                "write_shared_resource",
                {"resource_key": "X", "new_value": {"quantity": 0}, "expected_version": version},
            )
            assert result.is_error
    async with database.connect() as connection:
        assert (await repositories.get_resource(connection, "X")).version == 1


async def test_mcp_two_independent_runtime_clients_reproduce_race(mcp_client, database):
    a_read = asyncio.Event()
    b_written = asyncio.Event()

    async def worker_a():
        identity = ExecutionIdentity(run_id="http-race", agent_id="A", node_id="a_reason")
        async with mcp_client(identity) as client:
            read = await client.call_tool("read_shared_resource", {"resource_key": "X"})
            a_read.set()
            await b_written.wait()
            return await client.call_tool(
                "write_shared_resource",
                {"resource_key": "X", "new_value": {"quantity": 20},
                 "expected_version": read.structured_content["version"]},
            )

    async def worker_b():
        await a_read.wait()
        identity = ExecutionIdentity(run_id="http-race", agent_id="B", node_id="b_commit")
        async with mcp_client(identity) as client:
            read = await client.call_tool("read_shared_resource", {"resource_key": "X"})
            updated = await client.call_tool(
                "write_shared_resource",
                {"resource_key": "X", "new_value": {"quantity": 50},
                 "expected_version": read.structured_content["version"]},
            )
            assert updated.structured_content["version"] == 2
            b_written.set()

    conflict, _ = await asyncio.wait_for(
        asyncio.gather(worker_a(), worker_b()), timeout=15
    )
    assert conflict.structured_content["expected_version"] == 1
    assert conflict.structured_content["current_version"] == 2
    async with database.connect() as connection:
        logs = await repositories.get_access_logs(connection, "http-race")
        conflicts = await repositories.get_conflicts(connection, "http-race")
    assert [(row["agent_id"], row["operation"], row["version"]) for row in logs] == [
        ("A", "READ", 1), ("B", "READ", 1), ("B", "WRITE", 2)
    ]
    assert [(row["agent_id"], row["node_id"]) for row in conflicts] == [("A", "a_reason")]
