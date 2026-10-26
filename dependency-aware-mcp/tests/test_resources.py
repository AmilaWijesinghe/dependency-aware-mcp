"""File-backed resource storage and configuration behavior."""

import sqlite3

import pytest

from app.concurrency.conflicts import ResourceNotFound
from app.concurrency.provenance import execution_context
from app.storage import repositories
from app.storage.database import init_db


async def test_read_list_and_versioned_replacement(service, identity):
    with execution_context(identity):
        initial = await service.read("X")
        assert initial.version == 1
        assert initial.value == {"quantity": 100}
        assert [item.resource_key for item in await service.list()] == ["X"]
        updated = await service.write(
            "X", {"quantity": 50, "description": "සබන්", "details": {"tags": [1, True, None]}}, 1
        )
        assert updated.version == 2
        assert updated.updated_at
        assert (await service.read("X")).value == updated.value


async def test_missing_resource_is_typed_and_not_a_version_conflict(service, identity):
    with execution_context(identity):
        with pytest.raises(ResourceNotFound) as read:
            await service.read("missing")
        assert read.value.resource_key == "missing"
        with pytest.raises(ResourceNotFound):
            await service.write("missing", {"quantity": 1}, 1)
    async with service.database.connect() as connection:
        assert await repositories.get_conflicts(connection, identity.run_id) == []
        assert await repositories.get_access_logs(connection, identity.run_id) == []


async def test_init_is_idempotent_and_preserves_state(database, service, identity):
    with execution_context(identity):
        await service.write("X", {"quantity": 50}, 1)
    await init_db(database.path)
    await init_db(database.path)
    async with database.connect() as connection:
        resource = await repositories.get_resource(connection, "X")
        assert resource.version == 2
        assert resource.value == {"quantity": 50}
        async with connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ) as cursor:
            names = {row["name"] for row in await cursor.fetchall()}
    assert {"resources", "access_logs", "dependencies", "conflicts", "runs"} <= names


async def test_admin_creation_cannot_overwrite_existing_resource(database):
    with pytest.raises(sqlite3.IntegrityError):
        async with database.transaction() as connection:
            await repositories.create_resource(connection, "X", {"quantity": 0})
    async with database.connect() as connection:
        resource = await repositories.get_resource(connection, "X")
        assert resource.version == 1
        assert resource.value == {"quantity": 100}


@pytest.mark.parametrize("version", [0, -1, True, "1"])
async def test_invalid_expected_version_cannot_mutate(service, identity, version):
    with execution_context(identity):
        with pytest.raises(ValueError, match="positive integer"):
            await service.write("X", {"quantity": 0}, version)
        assert (await service.read("X")).version == 1
