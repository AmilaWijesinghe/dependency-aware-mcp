import logging

from mcp.server import MCPServer
from mcp.server.mcpserver import Context

from app.concurrency.middleware import (
    ConcurrencyMiddleware,
)
from app.storage.mongodb import resources

logging.basicConfig(
    level=logging.INFO,
    format=("%(asctime)s | " "%(levelname)s | " "%(name)s | " "%(message)s"),
)


mcp = MCPServer("Dependency Aware Shared State")


middleware = ConcurrencyMiddleware()


# ---------------------------------------------------------
# READ
# ---------------------------------------------------------


@mcp.tool()
async def read_shared_resource(
    resource_key: str,
    ctx: Context,
) -> dict:
    """
    Read a shared resource.

    The resource value and current version are returned.
    """

    return await middleware.read_shared_resource(
        resource_key=resource_key,
        ctx=ctx,
    )


# ---------------------------------------------------------
# WRITE
# ---------------------------------------------------------


@mcp.tool()
async def write_shared_resource(
    resource_key: str,
    new_value: dict,
    expected_version: int,
    ctx: Context,
) -> dict:
    """
    Update a shared resource only if its current version
    matches expected_version.
    """

    return await middleware.write_shared_resource(
        resource_key=resource_key,
        new_value=new_value,
        expected_version=(expected_version),
        ctx=ctx,
    )


# ---------------------------------------------------------
# LIST
# ---------------------------------------------------------


@mcp.tool()
async def list_shared_resources() -> list[dict]:
    """
    List shared resources and their current versions.
    """

    cursor = resources.find(
        {},
        {
            "_id": 1,
            "version": 1,
        },
    )

    documents = await cursor.to_list(length=100)

    return [
        {
            "resource_key": document["_id"],
            "version": document["version"],
        }
        for document in documents
    ]


@mcp.tool()
async def naive_write_shared_resource(
    resource_key: str,
    new_value: dict,
    ctx: Context,
) -> dict:
    """
    Baseline write without optimistic version validation.
    """

    return await middleware.naive_write_shared_resource(
        resource_key=resource_key,
        new_value=new_value,
        ctx=ctx,
    )


@mcp.tool()
async def acquire_resource_lock(
    resource_key: str,
    ctx: Context,
    lease_seconds: int = 30,
) -> dict:
    """
    Acquire an application-level exclusive resource lock.
    """

    return await middleware.acquire_resource_lock(
        resource_key=resource_key,
        ctx=ctx,
        lease_seconds=lease_seconds,
    )


@mcp.tool()
async def release_resource_lock(
    resource_key: str,
    ctx: Context,
) -> dict:

    return await middleware.release_resource_lock(
        resource_key=resource_key,
        ctx=ctx,
    )


@mcp.tool()
async def locked_write_shared_resource(
    resource_key: str,
    new_value: dict,
    ctx: Context,
) -> dict:

    return await middleware.locked_write_shared_resource(
        resource_key=resource_key,
        new_value=new_value,
        ctx=ctx,
    )


# ---------------------------------------------------------
# START SERVER
# ---------------------------------------------------------

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8001,
    )
