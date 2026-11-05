from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.storage.mongodb import (
    access_logs,
    benchmark_results,
    benchmark_runs,
    conflicts,
    dependencies,
    node_executions,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProvenanceRepository:
    """
    Stores MCP access provenance, dependencies,
    and structural version conflicts.
    """

    # -----------------------------------------------------
    # READ
    # -----------------------------------------------------

    async def record_read(
        self,
        *,
        run_id: str,
        agent_id: str,
        node_id: str,
        request_id: str,
        resource_key: str,
        version: int,
        value_snapshot: dict[str, Any],
    ) -> None:

        now = utc_now()

        # Access event
        await access_logs.insert_one(
            {
                "runId": run_id,
                "agentId": agent_id,
                "nodeId": node_id,
                "requestId": request_id,
                "resourceKey": resource_key,
                "operation": "READ",
                "version": version,
                "valueSnapshot": value_snapshot,
                "timestamp": now,
            }
        )

        # Dependency edge
        await dependencies.insert_one(
            {
                "runId": run_id,
                "agentId": agent_id,
                "nodeId": node_id,
                "resourceKey": resource_key,
                "readVersion": version,
                "readValue": value_snapshot,
                "timestamp": now,
            }
        )

    # -----------------------------------------------------
    # SUCCESSFUL WRITE
    # -----------------------------------------------------

    async def record_write(
        self,
        *,
        run_id: str,
        agent_id: str,
        node_id: str,
        request_id: str,
        resource_key: str,
        previous_version: int,
        new_version: int,
        value_snapshot: dict[str, Any],
    ) -> None:

        await access_logs.insert_one(
            {
                "runId": run_id,
                "agentId": agent_id,
                "nodeId": node_id,
                "requestId": request_id,
                "resourceKey": resource_key,
                "operation": "WRITE",
                "previousVersion": previous_version,
                "version": new_version,
                "valueSnapshot": value_snapshot,
                "timestamp": utc_now(),
            }
        )

    # -----------------------------------------------------
    # VERSION CONFLICT
    # -----------------------------------------------------

    async def record_conflict(
        self,
        *,
        run_id: str,
        agent_id: str,
        node_id: str,
        request_id: str,
        resource_key: str,
        expected_version: int,
        actual_version: int,
        attempted_value: dict[str, Any],
        current_value: dict[str, Any],
    ) -> None:

        await conflicts.insert_one(
            {
                "runId": run_id,
                "agentId": agent_id,
                "nodeId": node_id,
                "requestId": request_id,
                "resourceKey": resource_key,
                "expectedVersion": expected_version,
                "actualVersion": actual_version,
                "attemptedValue": attempted_value,
                "currentValue": current_value,
                # Phase 3 will populate these.
                "semanticResult": None,
                "confidence": None,
                "affectedPremises": [],
                "timestamp": utc_now(),
            }
        )


class NodeExecutionRepository:
    """
    Stores LangGraph node execution context.

    This gives the Semantic Auditor information about
    what an affected node was actually trying to do.
    """

    async def start_execution(
        self,
        *,
        run_id: str,
        agent_id: str,
        node_id: str,
        purpose: str,
        prompt: str,
    ) -> str:

        execution_id = str(uuid4())

        await node_executions.insert_one(
            {
                "_id": execution_id,
                "runId": run_id,
                "agentId": agent_id,
                "nodeId": node_id,
                "purpose": purpose,
                "prompt": prompt,
                "status": "running",
                "output": None,
                "error": None,
                "startedAt": utc_now(),
                "completedAt": None,
            }
        )

        return execution_id

    async def complete_execution(
        self,
        *,
        execution_id: str,
        output: str,
    ) -> None:

        await node_executions.update_one(
            {"_id": execution_id},
            {
                "$set": {
                    "status": "completed",
                    "output": output,
                    "completedAt": utc_now(),
                }
            },
        )

    async def fail_execution(
        self,
        *,
        execution_id: str,
        error: str,
    ) -> None:

        await node_executions.update_one(
            {"_id": execution_id},
            {
                "$set": {
                    "status": "failed",
                    "error": error,
                    "completedAt": utc_now(),
                }
            },
        )


class SemanticAuditRepository:
    """
    Loads evidence needed by the Semantic Auditor and
    persists the resulting semantic decision.
    """

    async def get_latest_conflict(
        self,
        *,
        run_id: str,
        agent_id: str,
        node_id: str,
        resource_key: str,
    ) -> dict | None:

        return await conflicts.find_one(
            {
                "runId": run_id,
                "agentId": agent_id,
                "nodeId": node_id,
                "resourceKey": resource_key,
            },
            sort=[("timestamp", -1)],
        )

    async def get_latest_dependency_before_conflict(
        self,
        *,
        run_id: str,
        agent_id: str,
        resource_key: str,
        before,
    ) -> dict | None:

        return await dependencies.find_one(
            {
                "runId": run_id,
                "agentId": agent_id,
                "resourceKey": resource_key,
                "timestamp": {"$lte": before},
            },
            sort=[("timestamp", -1)],
        )

    async def get_latest_node_execution(
        self,
        *,
        run_id: str,
        agent_id: str,
        node_id: str,
    ) -> dict | None:

        return await node_executions.find_one(
            {
                "runId": run_id,
                "agentId": agent_id,
                "nodeId": node_id,
            },
            sort=[("startedAt", -1)],
        )

    async def save_semantic_decision(
        self,
        *,
        conflict_id,
        semantic_result: str,
        confidence: float,
        affected_premises: list[str],
        reason: str,
        changed_fields: dict,
        intended_changes: dict,
        auditor_model: str,
    ) -> None:

        await conflicts.update_one(
            {"_id": conflict_id},
            {
                "$set": {
                    "semanticResult": semantic_result,
                    "confidence": confidence,
                    "affectedPremises": affected_premises,
                    "semanticReason": reason,
                    "changedFields": changed_fields,
                    "intendedChanges": intended_changes,
                    "auditorModel": auditor_model,
                    "auditedAt": utc_now(),
                }
            },
        )


class DependencyRepository:
    """
    Provides provenance dependencies for graph construction.
    """

    async def get_run_dependencies(
        self,
        *,
        run_id: str,
    ) -> list[dict]:

        return (
            await dependencies.find({"runId": run_id})
            .sort(
                "timestamp",
                1,
            )
            .to_list(length=1000)
        )


class RecoveryRepository:
    """
    Persists selective recovery planning and results.
    """

    async def get_latest_conflict(
        self,
        *,
        run_id: str,
        agent_id: str,
        node_id: str,
        resource_key: str,
    ) -> dict | None:

        return await conflicts.find_one(
            {
                "runId": run_id,
                "agentId": agent_id,
                "nodeId": node_id,
                "resourceKey": resource_key,
            },
            sort=[("timestamp", -1)],
        )

    async def save_recovery_plan(
        self,
        *,
        conflict_id,
        affected_nodes: list[str],
        preserved_nodes: list[str],
        strategy: str,
    ) -> None:

        await conflicts.update_one(
            {"_id": conflict_id},
            {
                "$set": {
                    "affectedNodes": affected_nodes,
                    "preservedNodes": preserved_nodes,
                    "recoveryStrategy": strategy,
                    "recoveryStatus": "planned",
                }
            },
        )

    async def save_recovery_result(
        self,
        *,
        conflict_id,
        status: str,
        result: dict,
    ) -> None:

        await conflicts.update_one(
            {"_id": conflict_id},
            {
                "$set": {
                    "recoveryStatus": status,
                    "recoveryResult": result,
                    "recoveredAt": utc_now(),
                }
            },
        )


class BenchmarkRepository:

    async def start_benchmark(
        self,
        *,
        benchmark_id: str,
        repetitions: int,
        protocols: list[str],
        scenarios: list[str],
        model: str,
        benchmark_seed: int | None = None,
        scenario_set: str | None = None,
    ) -> None:

        await benchmark_runs.insert_one(
            {
                "benchmarkId": benchmark_id,
                "status": "running",
                "repetitions": repetitions,
                "protocols": protocols,
                "scenarios": scenarios,
                "model": model,
                "startedAt": utc_now(),
                "completedAt": None,
                "benchmarkSeed": benchmark_seed,
                "scenarioSet": scenario_set,
            }
        )

    async def save_result(
        self,
        result: dict,
    ) -> None:

        result = dict(result)

        result["createdAt"] = utc_now()

        await benchmark_results.insert_one(result)

    async def complete_benchmark(
        self,
        *,
        benchmark_id: str,
    ) -> None:

        await benchmark_runs.update_one(
            {"benchmarkId": benchmark_id},
            {
                "$set": {
                    "status": "completed",
                    "completedAt": utc_now(),
                }
            },
        )
