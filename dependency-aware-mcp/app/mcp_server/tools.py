"""Model-facing MCP contracts; provenance comes only from runtime context."""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from pydantic import Field, JsonValue, ValidationError

from app.concurrency.conflicts import (
    MissingExecutionContext,
    ResourceNotFound,
    VersionConflict,
)
from app.concurrency.provenance import ExecutionIdentity, execution_context
from app.concurrency.version_manager import ResourceService

ResourceKey = Annotated[str, Field(min_length=1)]
ExpectedVersion = Annotated[int, Field(ge=1, strict=True)]


def _runtime_identity(ctx: Context) -> ExecutionIdentity:
    """Bridge a separate trusted runtime process to task-local provenance.

    Headers are a loopback research transport, not authentication. Never expose
    them as model arguments. ContextVars alone cannot cross a process boundary.
    """
    request = ctx.request_context.request
    if request is None:
        raise MissingExecutionContext("MCP HTTP runtime identity headers are required")
    headers = request.headers
    try:
        return ExecutionIdentity(
            run_id=headers.get("x-run-id", ""),
            agent_id=headers.get("x-agent-id", ""),
            node_id=headers.get("x-node-id", ""),
        )
    except ValidationError as error:
        raise MissingExecutionContext(
            "Runtime must supply X-Run-Id, X-Agent-Id and X-Node-Id headers"
        ) from error


async def _execute(
    ctx: Context, operation: Callable[[], Awaitable[dict[str, Any]]]
) -> dict[str, Any]:
    try:
        with execution_context(_runtime_identity(ctx)):
            return await operation()
    except VersionConflict as error:
        return error.as_result().model_dump()
    except ResourceNotFound as error:
        return {
            "status": "error",
            "error": "resource_not_found",
            "resource_key": error.resource_key,
        }
    except MissingExecutionContext:
        return {
            "status": "error",
            "error": "missing_execution_context",
            "message": "Runtime must supply X-Run-Id, X-Agent-Id and X-Node-Id headers",
        }


def register_tools(server: MCPServer, service: ResourceService) -> None:
    @server.tool()
    async def read_shared_resource(
        resource_key: ResourceKey, ctx: Context
    ) -> dict[str, Any]:
        """Read a shared resource's value and version."""
        async def read() -> dict[str, Any]:
            return (await service.read(resource_key)).model_dump()

        return await _execute(ctx, read)

    @server.tool()
    async def write_shared_resource(
        resource_key: ResourceKey,
        new_value: dict[str, JsonValue],
        expected_version: ExpectedVersion,
        ctx: Context,
    ) -> dict[str, Any]:
        """Replace a resource only if expected_version still matches its version."""
        async def write() -> dict[str, Any]:
            resource = await service.write(resource_key, new_value, expected_version)
            return {"status": "ok", **resource.model_dump()}

        return await _execute(ctx, write)

    @server.tool()
    async def list_shared_resources(ctx: Context) -> dict[str, Any]:
        """List shared resources including their current values and versions."""
        async def list_all() -> dict[str, Any]:
            return {
                "resources": [resource.model_dump() for resource in await service.list()]
            }

        return await _execute(ctx, list_all)
