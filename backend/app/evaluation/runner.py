import asyncio
import random
from copy import deepcopy
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from langchain_core.callbacks import (
    get_usage_metadata_callback,
)

from app.agents.auditor import SemanticAuditor
from app.config import settings
from app.concurrency.auditor_service import (
    calculate_diff,
)
from app.evaluation.metrics import (
    aggregate_callback_usage,
    gather_completed,
    preserve_failure_usage,
)
from app.evaluation.schemas import (
    BenchmarkResult,
    TokenUsage,
)
from app.evaluation.worker import BenchmarkWorker
from app.mcp_client.traced_tools import (
    extract_tool_data,
    traced_mcp_client,
)
from app.protocols.baselines import (
    run_2pl,
    run_naive,
    run_occ_full_restart,
)
from app.storage.mongodb import (
    benchmark_results,
    resources,
)
from app.storage.repositories import (
    BenchmarkRepository,
    SemanticAuditRepository,
)

from app.evaluation.isolation import (
    check_resource_response, execution_resource_key, initialize_resource, monitor_resource,
)


PROTOCOLS = [
    "naive",
    "2pl",
    "occ",
    "dependency_occ",
]

benchmark_repository = BenchmarkRepository()


def combine_usage(
    *usage_items: TokenUsage,
) -> TokenUsage:

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
            {"resource_key": resource_key},
        )

    data = check_resource_response(extract_tool_data(result), resource_key)

    if data.get("status") != "ok":
        raise RuntimeError(f"Read failed: {data}")

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
    if data.get("status") not in ("ok", "conflict"):
        raise RuntimeError(f"OCC write failed: {data}")
    return data


async def save_result(
    result: BenchmarkResult,
) -> None:

    document = result.to_dict()

    document["benchmarkId"] = document.pop("benchmark_id")

    document["runId"] = document.pop("run_id")

    document["resourceKey"] = document.pop("resource_key")

    document["scenarioId"] = document.pop("scenario_id")

    document["elapsedMs"] = document.pop("elapsed_ms")

    document["inputTokens"] = document.pop("input_tokens")

    document["outputTokens"] = document.pop("output_tokens")

    document["totalTokens"] = document.pop("total_tokens")

    document["wastedTokens"] = document.pop("wasted_tokens")

    document["lockWaitMs"] = document.pop("lock_wait_ms")

    document["nodesReexecuted"] = document.pop("nodes_reexecuted")

    document["nodesPreserved"] = document.pop("nodes_preserved")

    document["semanticPrediction"] = document.pop("semantic_prediction")

    document["semanticGroundTruth"] = document.pop("semantic_ground_truth")

    document["finalValue"] = document.pop("final_value")

    document["finalVersion"] = document.pop("final_version")

    document["createdAt"] = datetime.now(timezone.utc)

    await benchmark_results.insert_one(document)


# =========================================================
# DEPENDENCY-AWARE OCC
# =========================================================


@preserve_failure_usage
async def run_dependency_occ(
    *,
    benchmark_id: str,
    repetition: int,
    scenario,
) -> BenchmarkResult:

    run_id = str(uuid4())

    resource_key = execution_resource_key(benchmark_id, run_id)

    started = perf_counter()

    with monitor_resource(resource_key):
        try:

            await initialize_resource(resource_key=resource_key, initial_value=scenario.initial_value)
            initial = await read_resource(resource_key=resource_key, run_id=run_id, agent_id="initializer", node_id="initialize")
            if initial["version"] != 1 or initial["value"] != scenario.initial_value:
                raise RuntimeError("MCP initialization verification failed")

            # Initialization is infrastructure, outside protocol latency as before.
            started = perf_counter()

            worker_a = BenchmarkWorker("worker_a")

            worker_b = BenchmarkWorker("worker_b")

            # -------------------------------------------------
            # PREPARE
            #
            # This part is independent of shared-state values.
            # -------------------------------------------------

            (
                (
                    a_preparation,
                    a_prep_usage,
                ),
                (
                    b_preparation,
                    b_prep_usage,
                ),
            ) = await gather_completed(
                worker_a.prepare(
                    task=(scenario.worker_a_task),
                ),
                worker_b.prepare(
                    task=(scenario.worker_b_task),
                ),
            )

            # -------------------------------------------------
            # Both read v1.
            # -------------------------------------------------

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

            # -------------------------------------------------
            # Both decide using the same initial resource.
            # -------------------------------------------------

            (
                (
                    a_decision,
                    a_decision_usage,
                ),
                (
                    b_decision,
                    b_decision_usage,
                ),
            ) = await gather_completed(
                worker_a.decide(
                    task=(scenario.worker_a_task),
                    preparation=(a_preparation),
                    current_state=(a_snapshot["value"]),
                ),
                worker_b.decide(
                    task=(scenario.worker_b_task),
                    preparation=(b_preparation),
                    current_state=(b_snapshot["value"]),
                ),
            )

            # -------------------------------------------------
            # B commits first.
            # -------------------------------------------------

            if b_decision.action == "write" and b_decision.new_value is not None:

                b_result = await occ_write(
                    resource_key=resource_key,
                    run_id=run_id,
                    agent_id="worker_b",
                    node_id="b_commit",
                    new_value=(b_decision.new_value),
                    expected_version=(b_snapshot["version"]),
                )

                if b_result.get("status") != "ok":
                    raise RuntimeError("Worker B write failed: " f"{b_result}")

            # -------------------------------------------------
            # A attempts stale write.
            # -------------------------------------------------

            stale_result = {"status": "stopped"}

            if a_decision.action == "write" and a_decision.new_value is not None:

                stale_result = await occ_write(
                    resource_key=resource_key,
                    run_id=run_id,
                    agent_id="worker_a",
                    node_id="a_commit",
                    new_value=(a_decision.new_value),
                    expected_version=(a_snapshot["version"]),
                )

            conflicts = 0

            semantic_prediction = None

            auditor_usage = TokenUsage()

            recovery_usage = TokenUsage()

            wasted_tokens = 0

            nodes_reexecuted = 0
            nodes_preserved = 0

            # =================================================
            # CONFLICT
            # =================================================

            if stale_result.get("status") == "conflict":

                conflicts = 1

                current_snapshot = await read_resource(
                    resource_key=resource_key,
                    run_id=run_id,
                    agent_id=("auditor_context"),
                    node_id=("audit_read"),
                )

                old_state = a_snapshot["value"]

                current_state = current_snapshot["value"]

                attempted_state = a_decision.new_value or {}

                changed_fields = calculate_diff(
                    old_state,
                    current_state,
                )

                intended_changes = calculate_diff(
                    old_state,
                    attempted_state,
                )

                # ---------------------------------------------
                # Semantic Auditor
                # ---------------------------------------------

                auditor = SemanticAuditor()

                with get_usage_metadata_callback() as callback:

                    audit_decision = await auditor.classify(
                        worker_purpose=(scenario.worker_a_task),
                        old_state=(old_state),
                        current_state=(current_state),
                        attempted_state=(attempted_state),
                        changed_fields=(changed_fields),
                        intended_changes=(intended_changes),
                    )

                auditor_usage = aggregate_callback_usage(callback.usage_metadata)

                semantic_prediction = audit_decision.semantic_result

                # ---------------------------------------------
                # Persist audit decision into conflict record.
                # ---------------------------------------------

                audit_repository = SemanticAuditRepository()

                conflict_document = await audit_repository.get_latest_conflict(
                    run_id=run_id,
                    agent_id="worker_a",
                    node_id="a_commit",
                    resource_key=(resource_key),
                )

                if conflict_document is not None:

                    await audit_repository.save_semantic_decision(
                        conflict_id=(conflict_document["_id"]),
                        semantic_result=(audit_decision.semantic_result),
                        confidence=(audit_decision.confidence),
                        affected_premises=(audit_decision.affected_premises),
                        reason=(audit_decision.reason),
                        changed_fields=(changed_fields),
                        intended_changes=(intended_changes),
                        auditor_model=(auditor.model_name),
                    )

                # =================================================
                # NON-DISRUPTIVE
                # =================================================

                if semantic_prediction == "non_disruptive":

                    # A's reasoning remains valid.
                    #
                    # Apply ONLY A's intended field
                    # changes on top of current state.

                    rebased_value = deepcopy(current_state)

                    for (
                        field,
                        change,
                    ) in intended_changes.items():

                        rebased_value[field] = change["new"]

                    rebase_result = await occ_write(
                        resource_key=resource_key,
                        run_id=run_id,
                        agent_id=("worker_a"),
                        node_id=("rebase_a_commit"),
                        new_value=(rebased_value),
                        expected_version=(current_snapshot["version"]),
                    )

                    if rebase_result.get("status") != "ok":
                        raise RuntimeError("Rebase failed: " f"{rebase_result}")

                    # A_prepare, A_read and A_decide
                    # remain useful.
                    #
                    # B's four logical nodes remain useful.
                    nodes_preserved = 7

                    nodes_reexecuted = 0

                    wasted_tokens = 0

                # =================================================
                # DISRUPTIVE
                # =================================================

                else:

                    # Original A decision was based on stale state,
                    # so only that dependent reasoning is wasted.
                    #
                    # A preparation remains valid.

                    wasted_tokens = a_decision_usage.total_tokens

                    fresh_snapshot = await read_resource(
                        resource_key=resource_key,
                        run_id=run_id,
                        agent_id="worker_a",
                        node_id=("recover_a_read"),
                    )

                    (
                        recovery_decision,
                        recovery_usage,
                    ) = await worker_a.decide(
                        task=(scenario.worker_a_task),
                        # IMPORTANT:
                        # Preserve original preparation.
                        preparation=(a_preparation),
                        current_state=(fresh_snapshot["value"]),
                    )

                    if (
                        recovery_decision.action == "write"
                        and recovery_decision.new_value is not None
                    ):

                        recovery_result = await occ_write(
                            resource_key=resource_key,
                            run_id=run_id,
                            agent_id="worker_a",
                            node_id="recover_a_commit",
                            new_value=(recovery_decision.new_value),
                            expected_version=(fresh_snapshot["version"]),
                        )

                        if recovery_result.get("status") != "ok":
                            raise RuntimeError(
                                "Selective recovery " "failed: " f"{recovery_result}"
                            )

                        # read + decide + commit
                        nodes_reexecuted = 3

                    else:

                        # The fresh state invalidated the operation.
                        #
                        # Recovery successfully ends with STOP.
                        #
                        # Only:
                        # read + decide
                        #
                        # were rerun.
                        nodes_reexecuted = 2

                    # Preserved:
                    #
                    # A_prepare
                    # B_prepare
                    # B_read
                    # B_decide
                    # B_commit
                    nodes_preserved = 5

            # =================================================
            # FINAL VERIFICATION
            # =================================================

            final_snapshot = await read_resource(
                resource_key=resource_key, run_id=run_id, agent_id="verifier", node_id="verify",
            )
            final_resource = await resources.find_one({"_id": resource_key})

            if final_resource is None:
                raise RuntimeError("Final resource missing.")

            check_resource_response({"resource_key": resource_key, **final_resource}, resource_key)
            if final_snapshot["value"] != final_resource["value"] or final_snapshot["version"] != final_resource["version"]:
                raise RuntimeError("Final verification changed after protocol completion")
            correct = final_resource["value"] == scenario.expected_final

            total_usage = combine_usage(
                a_prep_usage,
                b_prep_usage,
                a_decision_usage,
                b_decision_usage,
                auditor_usage,
                recovery_usage,
            )

            return BenchmarkResult(
                benchmark_id=benchmark_id,
                run_id=run_id,
                resource_key=resource_key,
                repetition=repetition,
                protocol="dependency_occ",
                scenario_id=scenario.scenario_id,
                correct=correct,
                elapsed_ms=(perf_counter() - started) * 1000,
                input_tokens=(total_usage.input_tokens),
                output_tokens=(total_usage.output_tokens),
                total_tokens=(total_usage.total_tokens),
                wasted_tokens=(wasted_tokens),
                conflicts=conflicts,
                retries=0,
                lock_wait_ms=0.0,
                nodes_reexecuted=(nodes_reexecuted),
                nodes_preserved=(nodes_preserved),
                semantic_prediction=(semantic_prediction),
                semantic_ground_truth=(scenario.semantic_ground_truth),
                final_value=(final_resource["value"]),
                final_version=(final_resource["version"]),
            )

        except Exception as exc:

            return BenchmarkResult(
                benchmark_id=benchmark_id,
                run_id=run_id,
                resource_key=resource_key,
                repetition=repetition,
                protocol="dependency_occ",
                scenario_id=scenario.scenario_id,
                correct=False,
                elapsed_ms=(perf_counter() - started) * 1000,
                semantic_ground_truth=(scenario.semantic_ground_truth),
                error=str(exc),
            )


# =========================================================
# BASELINE WRAPPER
# =========================================================


@preserve_failure_usage
async def run_baseline(
    *,
    protocol: str,
    benchmark_id: str,
    repetition: int,
    scenario,
) -> BenchmarkResult:

    run_id = str(uuid4())

    resource_key = execution_resource_key(benchmark_id, run_id)

    started = perf_counter()

    with monitor_resource(resource_key):
        try:

            await initialize_resource(resource_key=resource_key, initial_value=scenario.initial_value)
            initial = await read_resource(resource_key=resource_key, run_id=run_id, agent_id="initializer", node_id="initialize")
            if initial["version"] != 1 or initial["value"] != scenario.initial_value:
                raise RuntimeError("MCP initialization verification failed")

            # Initialization is infrastructure, outside protocol latency as before.
            started = perf_counter()

            if protocol == "naive":

                result = await run_naive(
                    resource_key=resource_key,
                    run_id=run_id,
                    scenario=scenario,
                )

            elif protocol == "2pl":

                result = await run_2pl(
                    resource_key=resource_key,
                    run_id=run_id,
                    scenario=scenario,
                )

            elif protocol == "occ":

                result = await run_occ_full_restart(
                    resource_key=resource_key,
                    run_id=run_id,
                    scenario=scenario,
                )

            else:

                raise ValueError(f"Unknown protocol: " f"{protocol}")

            # ---------------------------------------------
            # IMPORTANT:
            # Re-check actual MongoDB state independently.
            # ---------------------------------------------

            final_resource = await resources.find_one({"_id": resource_key})

            if final_resource is None:
                raise RuntimeError("Final resource missing.")

            check_resource_response({"resource_key": resource_key, **final_resource}, resource_key)
            if final_resource["version"] != result.final_version or final_resource["value"] != result.final_value:
                raise RuntimeError("Final verification changed after protocol completion")
            actual_correct = final_resource["value"] == scenario.expected_final

            return BenchmarkResult(
                benchmark_id=benchmark_id,
                run_id=run_id,
                resource_key=resource_key,
                repetition=repetition,
                protocol=protocol,
                scenario_id=scenario.scenario_id,
                correct=actual_correct,
                elapsed_ms=result.elapsed_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                total_tokens=result.total_tokens,
                wasted_tokens=result.wasted_tokens,
                conflicts=result.conflicts,
                retries=result.retries,
                lock_wait_ms=result.lock_wait_ms,
                nodes_reexecuted=(result.nodes_reexecuted),
                nodes_preserved=(result.nodes_preserved),
                semantic_ground_truth=(scenario.semantic_ground_truth),
                final_value=(final_resource["value"]),
                final_version=(final_resource["version"]),
            )

        except Exception as exc:

            return BenchmarkResult(
                benchmark_id=benchmark_id,
                run_id=run_id,
                resource_key=resource_key,
                repetition=repetition,
                protocol=protocol,
                scenario_id=scenario.scenario_id,
                correct=False,
                elapsed_ms=(perf_counter() - started) * 1000,
                semantic_ground_truth=(scenario.semantic_ground_truth),
                error=str(exc),
            )


# =========================================================
# COMPLETE BENCHMARK
# =========================================================


async def run_benchmark(
    *,
    repetitions: int,
    scenarios: list,
    scenario_set: str,
    benchmark_seed: int,
) -> str:

    benchmark_id = str(uuid4())

    rng = random.Random(benchmark_seed)

    await benchmark_repository.start_benchmark(
        benchmark_id=benchmark_id,
        repetitions=repetitions,
        protocols=PROTOCOLS,
        scenarios=[scenario.scenario_id for scenario in scenarios],
        model=settings.ollama_model,
        benchmark_seed=benchmark_seed,
        scenario_set=scenario_set,
    )

    total_runs = len(scenarios) * len(PROTOCOLS) * repetitions

    print("\n================================")
    print("STARTING FAIR BENCHMARK")
    print("================================")

    print(
        "Benchmark ID:",
        benchmark_id,
    )

    print(
        "Model:",
        settings.ollama_model,
    )

    print(
        "Repetitions:",
        repetitions,
    )

    print(
        "Total runs:",
        total_runs,
    )

    completed = 0

    for repetition in range(
        1,
        repetitions + 1,
    ):

        # ---------------------------------------------
        # Randomize scenario order for each repetition.
        #
        # We use a fixed benchmark seed so the ordering
        # remains reproducible.
        # ---------------------------------------------

        scenario_order = scenarios.copy()

        rng.shuffle(scenario_order)

        for scenario in scenario_order:

            protocol_order = PROTOCOLS.copy()

            rng.shuffle(protocol_order)

            print("\n--------------------------------")

            print(
                "Repetition:",
                repetition,
            )

            print(
                "Scenario:",
                scenario.scenario_id,
            )

            print(
                "Expected final:",
                scenario.expected_final,
            )

            print(
                "Protocol order:",
                protocol_order,
            )

            print(
                "Scenario set:",
                scenario_set,
            )

            print(
                "Benchmark seed:",
                benchmark_seed,
            )

            for protocol in protocol_order:

                print(f"\nRunning {protocol}...")

                if protocol == "dependency_occ":

                    result = await run_dependency_occ(
                        benchmark_id=benchmark_id,
                        repetition=repetition,
                        scenario=scenario,
                    )

                else:

                    result = await run_baseline(
                        protocol=protocol,
                        benchmark_id=benchmark_id,
                        repetition=repetition,
                        scenario=scenario,
                    )

                await save_result(result)

                completed += 1

                print(
                    f"[{completed}/{total_runs}] "
                    f"{protocol} | "
                    f"correct={result.correct} | "
                    f"tokens={result.total_tokens} | "
                    f"wasted={result.wasted_tokens} | "
                    f"latency="
                    f"{result.elapsed_ms:.2f} ms"
                )

                if result.error:

                    print(
                        "ERROR:",
                        result.error,
                    )

    if completed != total_runs:
        raise RuntimeError(
            "Benchmark ended early: "
            f"{completed}/{total_runs} runs completed."
        )

    await benchmark_repository.complete_benchmark(benchmark_id=benchmark_id)

    print("\n================================")
    print("BENCHMARK FINISHED")
    print("================================")
    print("Scenario set:", scenario_set)

    print(
        "Benchmark seed:",
        benchmark_seed,
    )

    print(
        "Benchmark ID:",
        benchmark_id,
    )

    print(
        "Runs completed:",
        completed,
    )

    print("Expected runs:", total_runs)

    return benchmark_id
