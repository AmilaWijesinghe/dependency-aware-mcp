"""Runtime identity and provenance writes on the resource's transaction."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Annotated

import aiosqlite
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.concurrency.conflicts import MissingExecutionContext, VersionConflict

IdentityPart = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ExecutionIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: IdentityPart
    agent_id: IdentityPart
    node_id: IdentityPart


_current_identity: ContextVar[ExecutionIdentity | None] = ContextVar(
    "execution_identity", default=None
)


@contextmanager
def execution_context(identity: ExecutionIdentity) -> Iterator[None]:
    """Bind programmatic identity for this async task and reset it on every exit."""
    token = _current_identity.set(identity)
    try:
        yield
    finally:
        _current_identity.reset(token)


def require_identity() -> ExecutionIdentity:
    identity = _current_identity.get()
    if identity is None:
        raise MissingExecutionContext("Runtime execution identity is required")
    return identity


async def log_read(
    connection: aiosqlite.Connection,
    identity: ExecutionIdentity,
    resource_key: str,
    version: int,
) -> None:
    await connection.execute(
        """INSERT INTO access_logs
        (run_id, agent_id, node_id, resource_key, operation, version, timestamp)
        VALUES (?, ?, ?, ?, 'READ', ?, CURRENT_TIMESTAMP)""",
        (identity.run_id, identity.agent_id, identity.node_id, resource_key, version),
    )


async def log_write(
    connection: aiosqlite.Connection,
    identity: ExecutionIdentity,
    resource_key: str,
    version: int,
) -> None:
    """Log the committed version; its predecessor is version - 1."""
    await connection.execute(
        """INSERT INTO access_logs
        (run_id, agent_id, node_id, resource_key, operation, version, timestamp)
        VALUES (?, ?, ?, ?, 'WRITE', ?, CURRENT_TIMESTAMP)""",
        (identity.run_id, identity.agent_id, identity.node_id, resource_key, version),
    )


async def record_dependency(
    connection: aiosqlite.Connection,
    identity: ExecutionIdentity,
    resource_key: str,
    read_version: int,
) -> None:
    await connection.execute(
        """INSERT INTO dependencies
        (run_id, agent_id, node_id, resource_key, read_version, timestamp)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (
            identity.run_id, identity.agent_id, identity.node_id,
            resource_key, read_version,
        ),
    )


async def record_conflict(
    connection: aiosqlite.Connection,
    identity: ExecutionIdentity,
    conflict: VersionConflict,
) -> None:
    await connection.execute(
        """INSERT INTO conflicts
        (run_id, agent_id, node_id, resource_key,
         expected_version, actual_version, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (
            identity.run_id, identity.agent_id, identity.node_id,
            conflict.resource_key, conflict.expected_version, conflict.actual_version,
        ),
    )
