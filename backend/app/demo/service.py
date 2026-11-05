"""Observe the unchanged Phase 4 graph; publish only allowlisted facts.

Workers, MCP/OCC, Auditor, dependency analysis and recovery execute through
their existing implementations. No benchmark runner or model text is streamed.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from time import perf_counter

from langchain_core.callbacks import AsyncCallbackHandler

from app.concurrency.dependency_graph import DependencyGraphService, WORKER_NODES
from app.demo.events import DemoRun
from app.demo.scenarios import SCENARIOS, graph_input
from app.graph.phase4 import build_phase4_graph
from app.storage.mongodb import access_logs, conflicts, resources

logger = logging.getLogger(__name__)


def resource_state(value: dict, version: int) -> dict:
    return {"quantity": value["quantity"], "price": value["price"],
            "description": value["description"], "version": version}


def short_summary(value: str) -> str:
    return re.sub(r"<think\b[^>]*>.*?(?:</think>|$)", "", value,
                  flags=re.DOTALL | re.IGNORECASE).strip()[:600]


class TokenUsage(AsyncCallbackHandler):
    """Count provider-reported usage without retaining prompts or completions."""

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self.missing = False

    async def on_llm_end(self, response, **kwargs):
        self.calls += 1
        message = getattr(response.generations[0][0], "message", None)
        usage = getattr(message, "usage_metadata", None)
        if not isinstance(usage, dict) or not all(
            isinstance(usage.get(key), int) for key in ("input_tokens", "output_tokens")
        ):
            self.missing = True
            return
        self.input_tokens += usage["input_tokens"]
        self.output_tokens += usage["output_tokens"]

    def metrics(self):
        known = self.calls > 0 and not self.missing
        return {
            "inputTokens": self.input_tokens if known else None,
            "outputTokens": self.output_tokens if known else None,
            "totalTokens": self.input_tokens + self.output_tokens if known else None,
            # Nested agent usage cannot reliably be attributed to invalidated
            # outer nodes without changing the research implementation.
            "wastedTokens": None,
        }


async def execute_demo(run: DemoRun) -> None:
    started = perf_counter()
    try:
        async with asyncio.timeout(900):
            await _execute(run, started)
    except asyncio.CancelledError:
        await run.publish("demo_failed", {"message": "The demo stopped because the API shut down."})
        raise
    except Exception:
        logger.exception("Demo %s failed", run.demo_id)
        await run.publish("demo_failed", {
            "message": "Execution could not complete. Check MongoDB, MCP and Ollama, "
                       "then start a new run. Details are in the API log.",
        })


async def _execute(run: DemoRun, started: float) -> None:
    state = graph_input(run.demo_id, run.scenario)
    scenario = next(item for item in SCENARIOS if item["id"] == run.scenario)
    await run.publish("demo_started", {"scenario": run.scenario,
        "resourceKey": run.resource_key, "workerATask": scenario["workerATask"],
        "workerBTask": scenario["workerBTask"]})
    # Administrative initialization only. Workflow reads/writes all use MCP.
    await asyncio.wait_for(resources.insert_one({
        "_id": run.resource_key, "value": state["initial_value"], "version": 1,
        "updatedAt": datetime.now(timezone.utc),
    }), timeout=10)
    await run.publish("resource_initialized", {
        "resource": resource_state(state["initial_value"], 1), "resourceKey": run.resource_key,
    })
    usage = TokenUsage()
    recovery_nodes: list[str] = []
    recovery: dict = {}
    final = None
    graph = build_phase4_graph()

    async def access(node: str, operation: str) -> dict:
        document = await access_logs.find_one({
            "runId": run.demo_id, "resourceKey": run.resource_key,
            "nodeId": node, "operation": operation,
        }, sort=[("timestamp", -1)])
        if document is None:
            raise RuntimeError(f"Missing actual MCP provenance: {node}/{operation}")
        return document

    async for update in graph.astream(state, config={
        "configurable": {"thread_id": run.demo_id}, "callbacks": [usage],
    }, stream_mode="updates"):
        for node, result in update.items():
            if node in {"a_read", "b_read", "recover_a_read"}:
                document = await access(node, "READ")
                await run.publish("agent_read", {"agentId": document["agentId"], "nodeId": node,
                    "version": document["version"],
                    "resource": resource_state(document["valueSnapshot"], document["version"])})
                if node == "recover_a_read":
                    recovery_nodes.append(node)
                    await run.publish("recovery_step", {"nodeId": node, "summary": "Read fresh inventory through MCP."})
            elif node == "b_write":
                document = await access(node, "WRITE")
                if document["version"] != 2:
                    raise RuntimeError("Unexpected Worker B commit version")
                await run.publish("agent_decision", {"agentId": "worker_b", "summary": "Set quantity to 60."})
                await run.publish("resource_write", {"agentId": "worker_b", "nodeId": node,
                    "resource": resource_state(document["valueSnapshot"], document["version"])})
            elif node == "a_stale_write":
                conflict = await conflicts.find_one({"runId": run.demo_id,
                    "resourceKey": run.resource_key, "nodeId": node}, sort=[("timestamp", -1)])
                if conflict is None:
                    raise RuntimeError("Worker A did not produce an actual OCC conflict")
                attempted = conflict["attemptedValue"]
                summary = f"Proposed price = {attempted['price']}." if run.scenario == "non_disruptive" else f"Proposed remaining quantity = {attempted['quantity']}."
                await run.publish("agent_decision", {"agentId": "worker_a", "summary": summary})
                await run.publish("conflict_detected", {"agentId": "worker_a",
                    "expectedVersion": conflict["expectedVersion"], "actualVersion": conflict["actualVersion"]})
                await run.publish("semantic_audit_started", {})
            elif node == "semantic_audit":
                audit = result["audit_decision"]
                await run.publish("semantic_audit_completed", {
                    "semanticResult": audit["semantic_result"], "confidence": audit["confidence"],
                    "affectedPremises": [short_summary(item) for item in audit["affected_premises"]],
                    "reason": short_summary(audit["reason"]),
                })
            elif node == "dependency_scan":
                rebase = result["recovery_strategy"] == "rebase"
                affected = [] if rebase else result["affected_nodes"]
                preserved = sorted(WORKER_NODES) if rebase else result["preserved_nodes"]
                dependency_graph = await DependencyGraphService().build_graph(run_id=run.demo_id)
                recovery = {"strategy": "rebase" if rebase else "selective_reexecution",
                    "candidateNodes": result["affected_nodes"], "affectedNodes": affected,
                    "preservedNodes": preserved, "nodesPreserved": len(preserved),
                    "nodesReexecuted": 0, "reexecutedNodes": [],
                    "edges": [{"source": source, "target": target} for source, target in dependency_graph.edges]}
                await run.publish("dependency_analysis_completed", recovery)
                await run.publish("recovery_started", recovery)
            elif node == "recover_a_reason":
                recovery_nodes.append(node)
                decision = result["recovery_decision"]
                summary = "Recovery stopped the operation."
                if decision["action"] == "write":
                    summary = f"Recalculated remaining quantity = {decision['new_value']['quantity']}."
                await run.publish("agent_decision", {"agentId": "worker_a", "summary": summary})
                await run.publish("recovery_step", {"nodeId": node, "summary": summary})
            elif node in {"rebase_a", "recover_a_commit"}:
                if node == "recover_a_commit":
                    recovery_nodes.append(node)
                if result["recovery_result"].get("status") != "ok":
                    raise RuntimeError("Recovery did not commit successfully")
                document = await access(node, "WRITE")
                await run.publish("resource_write", {"agentId": "worker_a", "nodeId": node,
                    "resource": resource_state(document["valueSnapshot"], document["version"])})
                recovery = {**recovery, "nodesReexecuted": len(recovery_nodes),
                            "reexecutedNodes": list(recovery_nodes)}
                await run.publish("recovery_completed", recovery)
            elif node == "verify":
                verification = json.loads(result["verification"])
                if verification.get("status") != "ok":
                    raise RuntimeError("Final MCP verification failed")
                final = resource_state(verification["value"], verification["version"])

    expected = {"quantity": 60, "price": 25, "description": "Test Product", "version": 3} if run.scenario == "non_disruptive" else {"quantity": 30, "price": 20, "description": "Test Product", "version": 3}
    if final != expected:
        raise RuntimeError("Final state failed demo acceptance verification")
    await run.publish("final_state", {"resource": final, "verified": True})
    conflict_count = await conflicts.count_documents({"runId": run.demo_id, "resourceKey": run.resource_key})
    recovery_writes = await access_logs.count_documents({"runId": run.demo_id,
        "resourceKey": run.resource_key, "agentId": "worker_a", "operation": "WRITE"})
    await run.publish("metrics", {**usage.metrics(), "elapsedMs": round((perf_counter() - started) * 1000),
        "conflicts": conflict_count, "retries": recovery_writes,
        "nodesReexecuted": len(recovery_nodes), "nodesPreserved": recovery["nodesPreserved"]})
    await run.publish("demo_completed", {"verified": True})
