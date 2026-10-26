"""SQL operations on a caller-owned connection and transaction."""

import json
from typing import Any

import aiosqlite
from pydantic import JsonValue

from app.concurrency.conflicts import ResourceNotFound, VersionConflict
from app.schemas.resource import SharedResource


def _resource(row: aiosqlite.Row) -> SharedResource:
    return SharedResource(
        resource_key=row["resource_key"],
        value=json.loads(row["value_json"]),
        version=row["version"],
        updated_at=row["updated_at"],
    )


async def get_resource(
    connection: aiosqlite.Connection, resource_key: str
) -> SharedResource:
    async with connection.execute(
        "SELECT * FROM resources WHERE resource_key = ?", (resource_key,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise ResourceNotFound(resource_key)
    return _resource(row)


async def list_resources(connection: aiosqlite.Connection) -> list[SharedResource]:
    async with connection.execute(
        "SELECT * FROM resources ORDER BY resource_key"
    ) as cursor:
        return [_resource(row) for row in await cursor.fetchall()]


async def create_resource(
    connection: aiosqlite.Connection,
    resource_key: str,
    value: dict[str, JsonValue],
) -> SharedResource:
    """Administrative setup only; existing resources cannot be overwritten."""
    resource = SharedResource(resource_key=resource_key, value=value, version=1)
    await connection.execute(
        """INSERT INTO resources (resource_key, value_json, version, updated_at)
        VALUES (?, ?, 1, CURRENT_TIMESTAMP)""",
        (resource.resource_key, json.dumps(resource.value, allow_nan=False)),
    )
    return await get_resource(connection, resource_key)


async def update_resource(
    connection: aiosqlite.Connection,
    resource_key: str,
    new_value: dict[str, JsonValue],
    expected_version: int,
) -> SharedResource:
    """Compare and mutate in ONE conditional UPDATE, never a pre-read check.

    The caller must hold a transaction so the post-update snapshot and
    any conflict's actual_version refer to the same database operation.
    """
    if type(expected_version) is not int or expected_version < 1:
        raise ValueError("expected_version must be a positive integer")
    value_json = json.dumps(new_value, allow_nan=False)
    async with connection.execute(
        """UPDATE resources
        SET value_json = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
        WHERE resource_key = ? AND version = ?""",
        (value_json, resource_key, expected_version),
    ) as cursor:
        changed = cursor.rowcount
    resource = await get_resource(connection, resource_key)
    if changed == 0:
        raise VersionConflict(resource_key, expected_version, resource.version)
    return resource


async def get_access_logs(
    connection: aiosqlite.Connection, run_id: str
) -> list[dict[str, Any]]:
    async with connection.execute(
        "SELECT * FROM access_logs WHERE run_id = ? ORDER BY id", (run_id,)
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_dependencies(
    connection: aiosqlite.Connection, run_id: str
) -> list[dict[str, Any]]:
    async with connection.execute(
        "SELECT * FROM dependencies WHERE run_id = ? ORDER BY id", (run_id,)
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def get_conflicts(
    connection: aiosqlite.Connection, run_id: str
) -> list[dict[str, Any]]:
    async with connection.execute(
        "SELECT * FROM conflicts WHERE run_id = ? ORDER BY id", (run_id,)
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]
