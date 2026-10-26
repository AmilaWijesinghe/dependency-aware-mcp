"""Isolated file-backed databases and a real local Streamable HTTP server."""

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
import pytest
import uvicorn
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from app.config import Settings
from app.concurrency.provenance import ExecutionIdentity
from app.concurrency.version_manager import ResourceService
from app.mcp_server.server import create_server
from app.storage import repositories
from app.storage.database import Database, init_db


@pytest.fixture
async def database(tmp_path) -> Database:
    path = tmp_path / "data" / "test.db"
    await init_db(path)
    database = Database(path)
    async with database.transaction() as connection:
        await repositories.create_resource(connection, "X", {"quantity": 100})
    return database


@pytest.fixture
def service(database) -> ResourceService:
    return ResourceService(database)


@pytest.fixture
def identity() -> ExecutionIdentity:
    return ExecutionIdentity(run_id="run-test", agent_id="worker_a", node_id="a_reason")


@pytest.fixture
async def mcp_url(database) -> AsyncIterator[str]:
    config = Settings(_env_file=None, database_path=database.path)
    app = create_server(config).streamable_http_app(
        stateless_http=True, json_response=True
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    task.result()
                    raise RuntimeError("MCP test server stopped during startup")
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=10)
        finally:
            listener.close()


@pytest.fixture
def mcp_client(mcp_url):
    @asynccontextmanager
    async def connect(identity: ExecutionIdentity | None = None):
        headers = {}
        if identity is not None:
            headers = {
                "X-Run-Id": identity.run_id,
                "X-Agent-Id": identity.agent_id,
                "X-Node-Id": identity.node_id,
            }
        async with httpx2.AsyncClient(headers=headers, trust_env=False) as http:
            transport = streamable_http_client(mcp_url, http_client=http)
            async with Client(transport, read_timeout_seconds=5, cache=None) as client:
                yield client

    return connect
