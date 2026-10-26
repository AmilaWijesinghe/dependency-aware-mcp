"""Deterministic reproduction and atomic compare-and-swap behavior."""

import asyncio

import pytest

from app.concurrency.conflicts import VersionConflict
from app.concurrency.provenance import ExecutionIdentity, execution_context
from app.storage import repositories


async def test_stale_write_preserves_value_and_reports_versions(service, identity):
    with execution_context(identity):
        await service.write("X", {"quantity": 50}, 1)
        with pytest.raises(VersionConflict) as caught:
            await service.write("X", {"quantity": 20}, 1)
        conflict = caught.value
        assert (conflict.expected_version, conflict.actual_version) == (1, 2)
        assert conflict.as_result().model_dump() == {
            "status": "conflict", "resource_key": "X",
            "expected_version": 1, "current_version": 2,
        }
        current = await service.read("X")
    assert (current.version, current.value) == (2, {"quantity": 50})
    async with service.database.connect() as connection:
        conflicts = await repositories.get_conflicts(connection, identity.run_id)
        logs = await repositories.get_access_logs(connection, identity.run_id)
    assert len(conflicts) == 1
    assert conflicts[0]["actual_version"] == 2
    assert conflicts[0]["semantic_result"] is None
    assert [row["version"] for row in logs if row["operation"] == "WRITE"] == [2]


async def test_two_workers_force_read_write_stale_write(service):
    a_read = asyncio.Event()
    b_written = asyncio.Event()

    async def worker_a():
        with execution_context(
            ExecutionIdentity(run_id="race", agent_id="A", node_id="a_reason")
        ):
            snapshot = await service.read("X")
            a_read.set()
            await b_written.wait()
            with pytest.raises(VersionConflict) as caught:
                await service.write("X", {"quantity": 20}, snapshot.version)
            return caught.value

    async def worker_b():
        await a_read.wait()
        with execution_context(
            ExecutionIdentity(run_id="race", agent_id="B", node_id="b_commit")
        ):
            snapshot = await service.read("X")
            updated = await service.write("X", {"quantity": 50}, snapshot.version)
            b_written.set()
            return updated

    conflict, updated = await asyncio.wait_for(
        asyncio.gather(worker_a(), worker_b()), timeout=10
    )
    assert updated.version == conflict.actual_version == 2
    assert conflict.expected_version == 1


async def test_competing_writers_have_exactly_one_winner(service):
    start = asyncio.Event()

    async def writer(number):
        with execution_context(
            ExecutionIdentity(
                run_id="contended", agent_id=f"worker-{number}", node_id="commit"
            )
        ):
            await start.wait()
            return await service.write("X", {"winner": number}, 1)

    tasks = [asyncio.create_task(writer(i)) for i in range(8)]
    start.set()
    results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True), timeout=10
    )
    failures = [item for item in results if isinstance(item, VersionConflict)]
    winners = [item for item in results if not isinstance(item, BaseException)]
    assert len(winners) == 1
    assert len(failures) == 7
    assert all(item.actual_version == 2 for item in failures)
    async with service.database.connect() as connection:
        current = await repositories.get_resource(connection, "X")
        logs = await repositories.get_access_logs(connection, "contended")
        conflicts = await repositories.get_conflicts(connection, "contended")
    assert current == winners[0]
    assert len(logs) == 1
    assert logs[0]["operation"] == "WRITE"
    assert len(conflicts) == 7
