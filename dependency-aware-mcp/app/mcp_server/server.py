"""Separate MCP v2 server with Streamable HTTP at /mcp."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server import MCPServer

from app.config import Settings
from app.concurrency.version_manager import ResourceService
from app.mcp_server.tools import register_tools
from app.storage.database import Database, init_db


def create_server(settings: Settings | None = None) -> MCPServer:
    config = settings or Settings()
    database = Database(config.database_path)

    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[dict[str, Any]]:
        await init_db(database.path)
        yield {}

    server = MCPServer("Dependency Aware Shared State", lifespan=lifespan)
    register_tools(server, ResourceService(database))
    return server


def main() -> None:
    config = Settings()
    create_server(config).run(
        transport="streamable-http",
        host=config.mcp_host,
        port=config.mcp_port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
