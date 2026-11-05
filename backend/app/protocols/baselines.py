import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from time import perf_counter

from app.evaluation.schemas import (
    BenchmarkScenario,
    TokenUsage,
)
from app.evaluation.worker import BenchmarkWorker
from app.mcp_client.traced_tools import extract_tool_data, traced_mcp_client

from app.evaluation.isolation import check_resource_response
from app.evaluation.metrics import gather_completed

# Explicit release ends the critical section; TTL cleans abandoned ownership.
BENCHMARK_LOCK_LEASE_SECONDS = 3600


@dataclass
class ProtocolResult:
    protocol: str

    elapsed_ms: float

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    wasted_tokens: int = 0

    conflicts: int = 0
    retries: int = 0

    lock_wait_ms: float = 0.0

    nodes_reexecuted: int = 0
    nodes_preserved: int = 0

    final_value: dict | None = None
    final_version: int | None = None

    correct: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def combine_usage(
    *usage_items: TokenUsage,
) -> TokenUsage:
    """
    Sum token usage from multiple Ollama calls.
    """

    total = TokenUsage()

    for usage in usage_items:
        total = total + usage

    return total


async def read_resource(
    *,
    resource_key: str,
    run_id: str,
    agent_id: str,
    node_id: str,
) -> dict:

    async with traced_mcp_client(
        run_id=run_id,
        agent_id=agent_id,
        node_id=node_id,
    ) as client:

        result = await client.call_tool(
            "read_shared_resource",
            {
                "resource_key": resource_key,
            },
        )

    data = check_resource_response(extract_tool_data(result), resource_key)

    if data.get("status") != "ok":
        raise RuntimeError(f"Resource read failed: {data}")

    return data


async def final_read(
    *,
    resource_key: str,
    run_id: str,
) -> dict:

    return await read_resource(
        resource_key=resource_key,
        run_id=run_id,
        agent_id="verifier",
        node_id="verify",
    )


async def naive_write(
    *,
    resource_key: str,
    run_id: str,
    agent_id: str,
    node_id: str,
    new_value: dict,
) -> dict:

    async with traced_mcp_client(
        run_id=run_id,
        agent_id=agent_id,
        node_id=node_id,
    ) as client:

        result = await client.call_tool(
            "naive_write_shared_resource",
            {
                "resource_key": resource_key,
                "new_value": new_value,
            },
        )

    data = check_resource_response(extract_tool_data(result), resource_key)
    if data.get("status") not in ('ok',):
        raise RuntimeError(f"naive_write failed: {data}")
    return data


async def occ_write(
    *,
    resource_key: str,
    run_id: str,
    agent_id: str,
    node_id: str,
    new_value: dict,
    expected_version: int,
) -> dict:

    async with traced_mcp_client(
        run_id=run_id,
        agent_id=agent_id,
        node_id=node_id,
    ) as client:

        result = await client.call_tool(
            "write_shared_resource",
            {
                "resource_key": resource_key,
                "new_value": new_value,
                "expected_version": expected_version,
            },
        )

    data = check_resource_response(extract_tool_data(result), resource_key)
    if data.get("status") not in ('ok', 'conflict'):
        raise RuntimeError(f"occ_write failed: {data}")
    return data


async def acquire_until_success(
    *,
    resource_key: str,
    run_id: str,
    agent_id: str,
    node_id: str,
) -> float:
    """
    Acquire application-level lock.

    Returns lock waiting time in milliseconds.
    """

    started = perf_counter()

    while True:

        async with traced_mcp_client(
            run_id=run_id,
            agent_id=agent_id,
            node_id=node_id,
        ) as client:

            result = await client.call_tool(
                "acquire_resource_lock",
                {
                    "resource_key": resource_key,
                    "lease_seconds": BENCHMARK_LOCK_LEASE_SECONDS,
                },
            )

        data = check_resource_response(extract_tool_data(result), resource_key)

        if data.get("status") == "acquired":
            break

        if data.get("status") != "busy":
            raise RuntimeError(f"Lock acquisition failed: {data}")

        await asyncio.sleep(0.05)

    return (perf_counter() - started) * 1000


async def release_lock(
    *,
    resource_key: str,
    run_id: str,
    agent_id: str,
    node_id: str,
) -> None:

    async with traced_mcp_client(
        run_id=run_id,
        agent_id=agent_id,
        node_id=node_id,
    ) as client:

        result = await client.call_tool(
            "release_resource_lock",
            {
                "resource_key": resource_key,
            },
        )

    data = check_resource_response(extract_tool_data(result), resource_key)
    if data.get("status") != "released":
        raise RuntimeError(f"Lock release failed: {data}")


async def locked_write(
    *,
    resource_key: str,
    run_id: str,
    agent_id: str,
    node_id: str,
    new_value: dict,
) -> dict:

    async with traced_mcp_client(
        run_id=run_id,
        agent_id=agent_id,
        node_id=node_id,
    ) as client:

        result = await client.call_tool(
            "locked_write_shared_resource",
            {
                "resource_key": resource_key,
                "new_value": new_value,
            },
        )

    data = check_resource_response(extract_tool_data(result), resource_key)
    if data.get("status") not in ('ok',):
        raise RuntimeError(f"locked_write failed: {data}")
    return data


@asynccontextmanager
async def release_after(*, resource_key: str, run_id: str, agent_id: str, node_id: str):
    """Release explicitly, retaining both the critical-section and cleanup errors."""
    primary = None
    try:
        yield
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            await release_lock(
                resource_key=resource_key, run_id=run_id,
                agent_id=agent_id, node_id=node_id,
            )
        except Exception as cleanup:
            if primary is not None:
                raise RuntimeError(f"{primary}; cleanup error: {cleanup}") from primary
            raise


# =========================================================
# NAIVE
# =========================================================


async def run_naive(
    *,
    resource_key: str,
    run_id: str,
    scenario: BenchmarkScenario,
) -> ProtocolResult:

    started = perf_counter()

    worker_a = BenchmarkWorker("worker_a")

    worker_b = BenchmarkWorker("worker_b")

    # -----------------------------------------------------
    # Both workers perform the same preparation workload.
    # -----------------------------------------------------

    (
        (a_preparation, a_prep_usage),
        (b_preparation, b_prep_usage),
    ) = await gather_completed(
        worker_a.prepare(
            task=scenario.worker_a_task,
        ),
        worker_b.prepare(
            task=scenario.worker_b_task,
        ),
    )

    # -----------------------------------------------------
    # Both read v1.
    # -----------------------------------------------------

    a_snapshot, b_snapshot = await gather_completed(
        read_resource(
            resource_key=resource_key,
            run_id=run_id,
            agent_id="worker_a",
            node_id="a_read",
        ),
        read_resource(
            resource_key=resource_key,
            run_id=run_id,
            agent_id="worker_b",
            node_id="b_read",
        ),
    )

    # -----------------------------------------------------
    # Both reason from the same original state.
    # -----------------------------------------------------

    (
        (a_decision, a_decision_usage),
        (b_decision, b_decision_usage),
    ) = await gather_completed(
        worker_a.decide(
            task=scenario.worker_a_task,
            preparation=a_preparation,
            current_state=a_snapshot["value"],
        ),
        worker_b.decide(
            task=scenario.worker_b_task,
            preparation=b_preparation,
            current_state=b_snapshot["value"],
        ),
    )

    # -----------------------------------------------------
    # Worker B writes first.
    # -----------------------------------------------------

    if b_decision.action == "write" and b_decision.new_value is not None:
        await naive_write(
            resource_key=resource_key,
            run_id=run_id,
            agent_id="worker_b",
            node_id="b_commit",
            new_value=b_decision.new_value,
        )

    # -----------------------------------------------------
    # Worker A writes stale data WITHOUT validation.
    # -----------------------------------------------------

    if a_decision.action == "write" and a_decision.new_value is not None:
        await naive_write(
            resource_key=resource_key,
            run_id=run_id,
            agent_id="worker_a",
            node_id="a_commit",
            new_value=a_decision.new_value,
        )

    final = await final_read(resource_key=resource_key, run_id=run_id)

    usage = combine_usage(
        a_prep_usage,
        b_prep_usage,
        a_decision_usage,
        b_decision_usage,
    )

    correct = final["value"] == scenario.expected_final

    return ProtocolResult(
        protocol="naive",
        elapsed_ms=(perf_counter() - started) * 1000,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        # Naive does not abort/retry work.
        wasted_tokens=0,
        conflicts=0,
        retries=0,
        final_value=final["value"],
        final_version=final["version"],
        correct=correct,
    )


# =========================================================
# APPLICATION-LEVEL 2PL
# =========================================================


async def run_2pl(
    *,
    resource_key: str,
    run_id: str,
    scenario: BenchmarkScenario,
) -> ProtocolResult:

    started = perf_counter()

    worker_a = BenchmarkWorker("worker_a")

    worker_b = BenchmarkWorker("worker_b")

    (
        (a_preparation, a_prep_usage),
        (b_preparation, b_prep_usage),
    ) = await gather_completed(
        worker_a.prepare(
            task=scenario.worker_a_task,
        ),
        worker_b.prepare(
            task=scenario.worker_b_task,
        ),
    )

    a_decision_usage = TokenUsage()
    b_decision_usage = TokenUsage()

    lock_wait_total = 0.0
    b_has_lock = asyncio.Event()

    # -----------------------------------------------------
    # B runs first so the serialization order matches
    # the B-before-A interleaving used by OCC/Naive.
    # -----------------------------------------------------

    async def worker_b_transaction():

        nonlocal b_decision_usage
        nonlocal lock_wait_total

        wait_ms = await acquire_until_success(
            resource_key=resource_key,
            run_id=run_id,
            agent_id="worker_b",
            node_id="b_lock",
        )

        lock_wait_total += wait_ms
        b_has_lock.set()

        async with release_after(resource_key=resource_key, run_id=run_id, agent_id="worker_b", node_id="b_unlock"):
            snapshot = await read_resource(
                resource_key=resource_key,
                run_id=run_id,
                agent_id="worker_b",
                node_id="b_read",
            )

            decision, usage = await worker_b.decide(
                task=scenario.worker_b_task,
                preparation=b_preparation,
                current_state=snapshot["value"],
            )

            b_decision_usage = usage

            if decision.action == "write" and decision.new_value is not None:
                await locked_write(
                    resource_key=resource_key,
                    run_id=run_id,
                    agent_id="worker_b",
                    node_id="b_commit",
                    new_value=decision.new_value,
                )

    async def worker_a_transaction():

        nonlocal a_decision_usage
        nonlocal lock_wait_total

        # Match the B-before-A workload even if B's MCP connection is slower.
        # Once B owns the lock, A can contend and its wait is still measured.
        await b_has_lock.wait()

        wait_ms = await acquire_until_success(
            resource_key=resource_key,
            run_id=run_id,
            agent_id="worker_a",
            node_id="a_lock",
        )

        lock_wait_total += wait_ms

        async with release_after(resource_key=resource_key, run_id=run_id, agent_id="worker_a", node_id="a_unlock"):
            snapshot = await read_resource(
                resource_key=resource_key,
                run_id=run_id,
                agent_id="worker_a",
                node_id="a_read",
            )

            decision, usage = await worker_a.decide(
                task=scenario.worker_a_task,
                preparation=a_preparation,
                current_state=snapshot["value"],
            )

            a_decision_usage = usage

            if decision.action == "write" and decision.new_value is not None:
                await locked_write(
                    resource_key=resource_key,
                    run_id=run_id,
                    agent_id="worker_a",
                    node_id="a_commit",
                    new_value=decision.new_value,
                )

    transactions = [
        asyncio.create_task(worker_b_transaction()),
        asyncio.create_task(worker_a_transaction()),
    ]
    try:
        await asyncio.gather(*transactions)
    except BaseException as primary:
        # If B fails before acquiring, A may still be waiting for its signal.
        # Finish cancellation before returning the original protocol error.
        for transaction in transactions:
            transaction.cancel()
        outcomes = await asyncio.gather(*transactions, return_exceptions=True)
        extra_errors = [
            outcome for outcome in outcomes
            if isinstance(outcome, Exception) and outcome is not primary
        ]
        if extra_errors:
            raise RuntimeError(
                f"{primary}; concurrent cleanup error: " + "; ".join(map(str, extra_errors))
            ) from primary
        raise

    final = await final_read(resource_key=resource_key, run_id=run_id)

    usage = combine_usage(
        a_prep_usage,
        b_prep_usage,
        a_decision_usage,
        b_decision_usage,
    )

    correct = final["value"] == scenario.expected_final

    return ProtocolResult(
        protocol="2pl",
        elapsed_ms=(perf_counter() - started) * 1000,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        wasted_tokens=0,
        conflicts=0,
        retries=0,
        lock_wait_ms=lock_wait_total,
        nodes_reexecuted=0,
        nodes_preserved=0,
        final_value=final["value"],
        final_version=final["version"],
        correct=correct,
    )


# =========================================================
# FULL-RESTART OCC
# =========================================================


async def run_occ_full_restart(
    *,
    resource_key: str,
    run_id: str,
    scenario: BenchmarkScenario,
) -> ProtocolResult:

    started = perf_counter()

    worker_a = BenchmarkWorker("worker_a")

    worker_b = BenchmarkWorker("worker_b")

    conflicts = 0
    retries = 0

    nodes_reexecuted = 0
    nodes_preserved = 0

    # -----------------------------------------------------
    # Initial preparation
    # -----------------------------------------------------

    (
        (a_preparation, a_prep_usage),
        (b_preparation, b_prep_usage),
    ) = await gather_completed(
        worker_a.prepare(
            task=scenario.worker_a_task,
        ),
        worker_b.prepare(
            task=scenario.worker_b_task,
        ),
    )

    # -----------------------------------------------------
    # Both read v1.
    # -----------------------------------------------------

    a_snapshot, b_snapshot = await gather_completed(
        read_resource(
            resource_key=resource_key,
            run_id=run_id,
            agent_id="worker_a",
            node_id="a_read",
        ),
        read_resource(
            resource_key=resource_key,
            run_id=run_id,
            agent_id="worker_b",
            node_id="b_read",
        ),
    )

    # -----------------------------------------------------
    # Both make decisions based on v1.
    # -----------------------------------------------------

    (
        (a_decision, a_decision_usage),
        (b_decision, b_decision_usage),
    ) = await gather_completed(
        worker_a.decide(
            task=scenario.worker_a_task,
            preparation=a_preparation,
            current_state=a_snapshot["value"],
        ),
        worker_b.decide(
            task=scenario.worker_b_task,
            preparation=b_preparation,
            current_state=b_snapshot["value"],
        ),
    )

    # -----------------------------------------------------
    # B commits first.
    # -----------------------------------------------------

    if b_decision.action == "write" and b_decision.new_value is not None:
        b_result = await occ_write(
            resource_key=resource_key,
            run_id=run_id,
            agent_id="worker_b",
            node_id="b_commit",
            new_value=b_decision.new_value,
            expected_version=b_snapshot["version"],
        )

        if b_result.get("status") != "ok":
            raise RuntimeError(f"Worker B OCC write failed: " f"{b_result}")

    # -----------------------------------------------------
    # A attempts stale write.
    # -----------------------------------------------------

    stale_result = {"status": "stopped"}

    if a_decision.action == "write" and a_decision.new_value is not None:
        stale_result = await occ_write(
            resource_key=resource_key,
            run_id=run_id,
            agent_id="worker_a",
            node_id="a_commit",
            new_value=a_decision.new_value,
            expected_version=a_snapshot["version"],
        )

    restart_usage = TokenUsage()

    # -----------------------------------------------------
    # FULL RESTART
    # -----------------------------------------------------

    if stale_result.get("status") == "conflict":

        conflicts += 1
        retries += 1

        # Everything from A's original transaction is
        # considered discarded under full-restart OCC.
        wasted_usage = combine_usage(
            a_prep_usage,
            a_decision_usage,
        )

        # Full restart reruns:
        # A_prepare
        # A_read
        # A_decide
        # Commit is counted only if the fresh decision writes.
        nodes_reexecuted = 3

        # B's four logical nodes are retained.
        nodes_preserved = 4

        # ---------------------------------------------
        # Restart A from the beginning.
        # ---------------------------------------------

        (
            restarted_preparation,
            restarted_prep_usage,
        ) = await worker_a.prepare(
            task=scenario.worker_a_task,
        )

        fresh_snapshot = await read_resource(
            resource_key=resource_key,
            run_id=run_id,
            agent_id="worker_a",
            node_id="a_restart_read",
        )

        (
            restarted_decision,
            restarted_decision_usage,
        ) = await worker_a.decide(
            task=scenario.worker_a_task,
            preparation=restarted_preparation,
            current_state=fresh_snapshot["value"],
        )

        restart_usage = combine_usage(
            restarted_prep_usage,
            restarted_decision_usage,
        )

        if (
            restarted_decision.action == "write"
            and restarted_decision.new_value is not None
        ):
            restart_result = await occ_write(
                resource_key=resource_key,
                run_id=run_id,
                agent_id="worker_a",
                node_id="a_restart_commit",
                new_value=(restarted_decision.new_value),
                expected_version=(fresh_snapshot["version"]),
            )

            if restart_result.get("status") != "ok":
                raise RuntimeError("Full OCC restart failed: " f"{restart_result}")

            nodes_reexecuted += 1

    else:
        wasted_usage = TokenUsage()

    final = await final_read(resource_key=resource_key, run_id=run_id)

    usage = combine_usage(
        a_prep_usage,
        b_prep_usage,
        a_decision_usage,
        b_decision_usage,
        restart_usage,
    )

    correct = final["value"] == scenario.expected_final

    return ProtocolResult(
        protocol="occ",
        elapsed_ms=(perf_counter() - started) * 1000,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        wasted_tokens=(wasted_usage.total_tokens),
        conflicts=conflicts,
        retries=retries,
        lock_wait_ms=0.0,
        nodes_reexecuted=(nodes_reexecuted),
        nodes_preserved=(nodes_preserved),
        final_value=final["value"],
        final_version=final["version"],
        correct=correct,
    )
