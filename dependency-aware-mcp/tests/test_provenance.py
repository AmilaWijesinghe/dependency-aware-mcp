"""Audit consistency and task-local identity isolation."""

import asyncio
import sqlite3

import pytest

from app.concurrency.conflicts import MissingExecutionContext
from app.concurrency.provenance import (
    ExecutionIdentity,
    execution_context,
    require_identity,
)
from app.storage import repositories


async def test_read_write_provenance_and_dependency(service, identity):
    with execution_context(identity):
        await service.read("X")
        await service.write("X", {"quantity": 50}, 1)
    async with service.database.connect() as connection:
        logs = await repositories.get_access_logs(connection, identity.run_id)
        dependencies = await repositories.get_dependencies(connection, identity.run_id)
    assert [(row["operation"], row["version"]) for row in logs] == [
        ("READ", 1), ("WRITE", 2)
    ]
    assert len(dependencies) == 1
    assert dependencies[0]["read_version"] == 1
    for row in [*logs, *dependencies]:
        assert (row["run_id"], row["agent_id"], row["node_id"]) == (
            identity.run_id, identity.agent_id, identity.node_id
        )
        assert row["timestamp"]


async def test_listing_values_records_read_dependencies(service, identity):
    with execution_context(identity):
        await service.list()
    async with service.database.connect() as connection:
        logs = await repositories.get_access_logs(connection, identity.run_id)
        deps = await repositories.get_dependencies(connection, identity.run_id)
    assert [(row["resource_key"], row["operation"]) for row in logs] == [("X", "READ")]
    assert [(row["resource_key"], row["read_version"]) for row in deps] == [("X", 1)]


async def test_write_rolls_back_if_audit_insert_fails(service, identity):
    async with service.database.transaction() as connection:
        await connection.execute(
            """CREATE TRIGGER fail_write_log BEFORE INSERT ON access_logs
            WHEN NEW.operation = 'WRITE'
            BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END"""
        )
    with execution_context(identity):
        with pytest.raises(sqlite3.IntegrityError, match="audit unavailable"):
            await service.write("X", {"quantity": 0}, 1)
    async with service.database.connect() as connection:
        current = await repositories.get_resource(connection, "X")
        assert (current.version, current.value) == (1, {"quantity": 100})
        assert await repositories.get_access_logs(connection, identity.run_id) == []


async def test_read_log_rolls_back_if_dependency_insert_fails(service, identity):
    async with service.database.transaction() as connection:
        await connection.execute(
            """CREATE TRIGGER fail_dependency BEFORE INSERT ON dependencies
            BEGIN SELECT RAISE(ABORT, 'dependency unavailable'); END"""
        )
    with execution_context(identity):
        with pytest.raises(sqlite3.IntegrityError, match="dependency unavailable"):
            await service.read("X")
    async with service.database.connect() as connection:
        assert await repositories.get_access_logs(connection, identity.run_id) == []
        assert await repositories.get_dependencies(connection, identity.run_id) == []


async def test_missing_context_is_rejected(service):
    for operation in [
        service.read("X"), service.list(), service.write("X", {"quantity": 0}, 1)
    ]:
        with pytest.raises(MissingExecutionContext):
            await operation


async def test_concurrent_contexts_are_isolated_and_reset(service):
    a_ready = asyncio.Event()
    b_ready = asyncio.Event()

    async def worker(name, ready, other_ready):
        identity = ExecutionIdentity(run_id=f"run-{name}", agent_id=name, node_id="read")
        with execution_context(identity):
            ready.set()
            await other_ready.wait()
            await service.read("X")
            assert require_identity() == identity
        with pytest.raises(MissingExecutionContext):
            require_identity()

    await asyncio.wait_for(
        asyncio.gather(
            worker("A", a_ready, b_ready),
            worker("B", b_ready, a_ready),
        ), timeout=10
    )
    async with service.database.connect() as connection:
        for name in ["A", "B"]:
            logs = await repositories.get_access_logs(connection, f"run-{name}")
            assert len(logs) == 1
            assert logs[0]["agent_id"] == name


def test_context_is_restored_after_exception(identity):
    with execution_context(identity):
        with pytest.raises(RuntimeError):
            with execution_context(
                ExecutionIdentity(run_id="inner", agent_id="B", node_id="commit")
            ):
                raise RuntimeError("controlled failure")
        assert require_identity() == identity
    with pytest.raises(MissingExecutionContext):
        require_identity()
