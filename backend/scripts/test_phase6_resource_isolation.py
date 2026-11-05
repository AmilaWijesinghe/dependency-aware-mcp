"""Live MongoDB/MCP isolation and error-accounting infrastructure checks."""

import argparse
import asyncio
from uuid import uuid4
from unittest.mock import patch

from app.evaluation import runner
from app.evaluation.isolation import (
    check_resource_response, execution_resource_key, initialize_resource, monitor_resource,
)
from app.evaluation.scenarios import SCENARIOS
from app.evaluation.heldout_scenarios import HELDOUT_SCENARIOS
from app.mcp_client.traced_tools import extract_tool_data, traced_mcp_client
from app.protocols import baselines
from app.storage.mongodb import (
    access_logs, benchmark_results, benchmark_runs, close_database, conflicts,
    dependencies, ensure_indexes, ping_database, resource_locks, resources,
)


async def tool(name, *, key, run_id, agent="worker_a", node="test", **arguments):
    async with traced_mcp_client(run_id=run_id, agent_id=agent, node_id=node) as client:
        result = await client.call_tool(name, {"resource_key": key, **arguments})
    return check_resource_response(extract_tool_data(result), key)


async def verify_benchmark(benchmark_id: str, expected_runs: int) -> None:
    """Check persisted identity, provenance, versions, and infrastructure failures."""
    metadata = await benchmark_runs.find_one({"benchmarkId": benchmark_id})
    assert metadata and metadata["status"] == "completed", metadata
    results = await benchmark_results.find({"benchmarkId": benchmark_id}).to_list(None)
    assert len(results) == expected_runs, len(results)
    keys = [result.get("resourceKey") for result in results]
    assert all(keys) and len(set(keys)) == expected_runs, "Resource keys are not unique"
    assert len({result["runId"] for result in results}) == expected_runs
    scenarios = {scenario.scenario_id: scenario for scenario in SCENARIOS + HELDOUT_SCENARIOS}
    for result in results:
        key, run_id = result["resourceKey"], result["runId"]
        assert key == execution_resource_key(benchmark_id, run_id), result
        assert not result.get("error"), result
        accesses, deps, collisions, final, lock = await asyncio.gather(
            access_logs.find({"runId": run_id}).sort("timestamp", 1).to_list(None),
            dependencies.find({"runId": run_id}).to_list(None),
            conflicts.find({"runId": run_id}).to_list(None),
            resources.find_one({"_id": key}),
            resource_locks.find_one({"_id": key}),
        )
        assert accesses and deps, f"Missing provenance: {run_id}"
        assert accesses[0]["nodeId"] == "initialize" and accesses[0]["version"] == 1
        assert accesses[0]["valueSnapshot"] == scenarios[result["scenarioId"]].initial_value
        assert all(event["resourceKey"] == key for event in accesses + deps + collisions)
        assert all(event["agentId"] == "worker_a" and event["nodeId"] == "a_commit"
                   and result["protocol"] in ("occ", "dependency_occ")
                   for event in collisions), f"Unexpected conflict: {collisions}"
        version = 1
        writes = []
        for event in accesses:
            if event["operation"] == "WRITE":
                assert event["previousVersion"] == version, event
                assert event["version"] == version + 1, event
                version += 1
                writes.append(event)
            else:
                assert event["version"] >= version, f"Version rollback: {event}"
        assert final and final["version"] == result["finalVersion"] == version
        assert final["value"] == result["finalValue"]
        if writes:
            assert final["value"] == writes[-1]["valueSnapshot"], "Final-state contamination"
        assert lock is None, f"Lock leaked: {key}"
    print(f"Benchmark ID: {benchmark_id}", flush=True)
    print(f"Runs verified: {len(results)}/{expected_runs}", flush=True)
    print(f"Unique resourceKey values: {len(set(keys))}", flush=True)
    print("Unexpected Worker B/recovery conflicts: 0", flush=True)
    print("Lock release not_owner errors: 0", flush=True)
    print("Version rollback errors: 0", flush=True)
    print("Cross-run contamination: 0", flush=True)
    print(f"Resource example 1: {keys[0]}", flush=True)
    print(f"Resource example 2: {keys[1]}", flush=True)


async def main():
    await ping_database()
    await ensure_indexes()
    suite_id = str(uuid4())
    key_a = execution_resource_key(suite_id, "run_a")
    key_b = execution_resource_key(suite_id, "run_b")
    initial_a = {"quantity": 100, "price": 20, "description": "A"}
    initial_b = {"quantity": 50, "price": 10, "description": "B"}
    await asyncio.gather(
        initialize_resource(resource_key=key_a, initial_value=initial_a),
        initialize_resource(resource_key=key_b, initial_value=initial_b),
    )
    a, b = await asyncio.gather(
        tool("read_shared_resource", key=key_a, run_id="run_a"),
        tool("read_shared_resource", key=key_b, run_id="run_b"),
    )
    assert (a["value"], a["version"]) == (initial_a, 1)
    assert (b["value"], b["version"]) == (initial_b, 1)
    try:
        await initialize_resource(resource_key=key_a, initial_value=initial_b)
    except Exception as exc:
        from pymongo.errors import DuplicateKeyError
        assert isinstance(exc, DuplicateKeyError), exc
    else:
        raise AssertionError("Initialization reset an existing execution")
    print("RESOURCE ISOLATION: PASS", flush=True)

    async def execution(key, run_id, initial, quantities):
        with monitor_resource(key):
            for version, quantity in enumerate(quantities, 1):
                value = {**initial, "quantity": quantity}
                result = await tool("write_shared_resource", key=key, run_id=run_id,
                                    new_value=value, expected_version=version)
                assert result["status"] == "ok" and result["version"] == version + 1
            final = await tool("read_shared_resource", key=key, run_id=run_id)
            assert final["value"] == {**initial, "quantity": quantities[-1]}
            assert final["version"] == len(quantities) + 1
    await asyncio.gather(execution(key_a, "run_a", initial_a, [90, 80]),
                         execution(key_b, "run_b", initial_b, [40]))
    print("CONCURRENT RESOURCE ISOLATION: PASS", flush=True)

    async def acquire(key, run_id, agent="worker_a"):
        return await tool("acquire_resource_lock", key=key, run_id=run_id, agent=agent,
                          lease_seconds=baselines.BENCHMARK_LOCK_LEASE_SECONDS)
    async def release(key, run_id, agent="worker_a"):
        return await tool("release_resource_lock", key=key, run_id=run_id, agent=agent,
                          node="different_release_node")
    locks = await asyncio.gather(acquire(key_a, "run_a"), acquire(key_b, "run_b"))
    assert all(lock["status"] == "acquired" for lock in locks), locks
    for key in [key_a, key_b]:
        lock = await resource_locks.find_one({"_id": key})
        assert (lock["expiresAt"] - lock["acquiredAt"]).total_seconds() == 3600
    releases = await asyncio.gather(release(key_a, "run_a"), release(key_b, "run_b"))
    assert all(lock["status"] == "released" for lock in releases), releases
    print("2PL DIFFERENT-RESOURCE LOCKS: PASS", flush=True)

    assert (await acquire(key_a, "run_a"))["status"] == "acquired"
    assert (await acquire(key_a, "run_a", "worker_b"))["status"] == "busy"
    assert (await release(key_a, "run_b"))["status"] == "not_owner"
    assert (await release(key_a, "run_a", "worker_b"))["status"] == "not_owner"
    assert (await release(key_a, "run_a"))["status"] == "released"
    assert (await acquire(key_a, "run_b"))["status"] == "acquired"
    assert (await release(key_a, "run_b"))["status"] == "released"
    print("2PL SAME-RESOURCE EXCLUSION: PASS", flush=True)
    print("2PL lease: 3600 seconds; run/agent ownership; explicit release", flush=True)

    # Real Worker preparation and decisions; inject only the subsequent verifier error.
    async def fail_verification(**kwargs):
        raise RuntimeError("controlled verification failure after real LLM work")
    with patch.object(baselines, "final_read", side_effect=fail_verification):
        failed = await runner.run_baseline(
            protocol="naive", benchmark_id=suite_id, repetition=1, scenario=SCENARIOS[0],
        )
    assert failed.error and "controlled verification failure" in failed.error, failed
    assert failed.total_tokens > 0 and failed.input_tokens > 0 and failed.output_tokens > 0
    print(f"Controlled failure tokens: input={failed.input_tokens}, output={failed.output_tokens}, total={failed.total_tokens}", flush=True)
    print("TOKEN PRESERVATION ON FAILURE: PASS", flush=True)

    real_release = baselines.release_lock
    async def failed_write(**kwargs):
        raise RuntimeError("controlled primary write failure")
    async def failed_cleanup(**kwargs):
        await real_release(**kwargs)
        raise RuntimeError("controlled cleanup failure after explicit release")
    with (patch.object(baselines, "locked_write", side_effect=failed_write),
          patch.object(baselines, "release_lock", side_effect=failed_cleanup)):
        failed_2pl = await runner.run_baseline(
            protocol="2pl", benchmark_id=suite_id, repetition=1, scenario=SCENARIOS[0],
        )
    assert "controlled primary write failure" in failed_2pl.error, failed_2pl
    assert "controlled cleanup failure" in failed_2pl.error, failed_2pl
    assert failed_2pl.total_tokens > 0
    assert await resource_locks.find_one({"_id": failed_2pl.resource_key}) is None
    print(f"Primary and cleanup errors preserved: {failed_2pl.error}", flush=True)
    print(f"2PL controlled failure tokens: {failed_2pl.total_tokens}", flush=True)
    print("ALL PHASE 6 ISOLATION TESTS PASSED", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-id", help="Audit an already completed benchmark")
    parser.add_argument("--expected-runs", type=int)
    args = parser.parse_args()
    if bool(args.benchmark_id) != (args.expected_runs is not None):
        parser.error("--benchmark-id and --expected-runs must be supplied together")

    async def run():
        try:
            if args.benchmark_id:
                await verify_benchmark(args.benchmark_id, args.expected_runs)
            else:
                await main()
        finally:
            await close_database()
    asyncio.run(run())
