import json
import logging

from langgraph.checkpoint.memory import (
    InMemorySaver,
)
from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from app.agents.recovery_planner import (
    RecoveryPlanner,
)
from app.agents.workers import (
    create_worker,
)
from app.concurrency.auditor_service import (
    SemanticAuditorService,
)
from app.concurrency.dependency_graph import (
    DependencyGraphService,
)
from app.concurrency.recovery_service import (
    RecoveryService,
)
from app.graph.state import (
    Phase4State,
)
from app.mcp_client.traced_tools import (
    extract_tool_data,
    traced_mcp_client,
    traced_mcp_tools,
)
from app.storage.repositories import (
    NodeExecutionRepository,
    RecoveryRepository,
)

logger = logging.getLogger(__name__)


node_repository = NodeExecutionRepository()


def final_text(
    result: dict,
) -> str:

    messages = result.get(
        "messages",
        [],
    )

    if not messages:
        return ""

    content = messages[-1].content

    if isinstance(
        content,
        str,
    ):
        return content

    return str(content)


async def invoke_worker(
    *,
    state: Phase4State,
    agent_id: str,
    node_id: str,
    purpose: str,
    prompt: str,
    allowed_tools: set[str],
) -> str:

    execution_id = await node_repository.start_execution(
        run_id=state["run_id"],
        agent_id=agent_id,
        node_id=node_id,
        purpose=purpose,
        prompt=prompt,
    )

    try:

        async with traced_mcp_tools(
            run_id=state["run_id"],
            agent_id=agent_id,
            node_id=node_id,
        ) as all_tools:

            tools = [tool for tool in all_tools if tool.name in allowed_tools]

            worker = create_worker(
                name=agent_id,
                tools=tools,
            )

            result = await worker.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ]
                }
            )

            text = final_text(result)

            await node_repository.complete_execution(
                execution_id=(execution_id),
                output=text,
            )

            return text

    except Exception as exc:

        await node_repository.fail_execution(
            execution_id=(execution_id),
            error=str(exc),
        )

        raise


def build_phase4_graph():

    auditor_service = SemanticAuditorService()

    dependency_service = DependencyGraphService()

    recovery_service = RecoveryService()

    recovery_repository = RecoveryRepository()

    recovery_planner = RecoveryPlanner()

    # =====================================================
    # ORIGINAL EXECUTION
    # =====================================================

    async def a_read(
        state: Phase4State,
    ) -> dict:

        text = await invoke_worker(
            state=state,
            agent_id="worker_a",
            node_id="a_read",
            purpose=("Read the initial shared resource " "snapshot used by Worker A."),
            prompt=f"""
Use read_shared_resource to read:

{state["resource_key"]}

Do not modify anything.

Report the full resource value and version.
""",
            allowed_tools={"read_shared_resource"},
        )

        return {"worker_a_read": text}

    async def b_read(
        state: Phase4State,
    ) -> dict:

        text = await invoke_worker(
            state=state,
            agent_id="worker_b",
            node_id="b_read",
            purpose=("Read the initial shared resource " "snapshot used by Worker B."),
            prompt=f"""
Use read_shared_resource to read:

{state["resource_key"]}

Do not modify anything.

Report the full value and version.
""",
            allowed_tools={"read_shared_resource"},
        )

        return {"worker_b_read": text}

    async def b_write(
        state: Phase4State,
    ) -> dict:

        value_json = json.dumps(
            state["b_write_value"],
            indent=2,
        )

        text = await invoke_worker(
            state=state,
            agent_id="worker_b",
            node_id="b_write",
            purpose=(
                "Worker B updates the shared " "resource before Worker A commits."
            ),
            prompt=f"""
Use write_shared_resource directly.

Do NOT read again.

Resource:
{state["resource_key"]}

expected_version:
{state["initial_version"]}

Write this complete value:

{value_json}

Stop after the write result.
""",
            allowed_tools={"write_shared_resource"},
        )

        return {"worker_b_write": text}

    async def a_stale_write(
        state: Phase4State,
    ) -> dict:

        stale_json = json.dumps(
            state["a_stale_write_value"],
            indent=2,
        )

        purpose = state["a_task_purpose"]

        text = await invoke_worker(
            state=state,
            agent_id="worker_a",
            node_id="a_stale_write",
            purpose=purpose,
            prompt=f"""
Continue using your OLD resource snapshot.

Do NOT read again.

TASK:

{purpose}

Use write_shared_resource directly.

Resource:
{state["resource_key"]}

expected_version:
{state["initial_version"]}

Attempt this complete value:

{stale_json}

If the write returns status='conflict':

STOP.

Do not retry.
""",
            allowed_tools={"write_shared_resource"},
        )

        return {"worker_a_stale_write": text}

    # =====================================================
    # SEMANTIC AUDIT
    # =====================================================

    async def semantic_audit(
        state: Phase4State,
    ) -> dict:

        decision = await auditor_service.audit_conflict(
            run_id=state["run_id"],
            agent_id="worker_a",
            node_id="a_stale_write",
            resource_key=(state["resource_key"]),
        )

        return {"audit_decision": decision.model_dump()}

    # =====================================================
    # DEPENDENCY SCAN
    # =====================================================

    async def dependency_scan(
        state: Phase4State,
    ) -> dict:

        affected, preserved = await dependency_service.find_affected_nodes(
            run_id=state["run_id"],
            agent_id="worker_a",
            resource_key=(state["resource_key"]),
            stale_version=(state["initial_version"]),
        )

        semantic_result = state["audit_decision"]["semantic_result"]

        if semantic_result == "non_disruptive":
            strategy = "rebase"

        else:
            strategy = "selective_rerun"

        conflict = await recovery_repository.get_latest_conflict(
            run_id=state["run_id"],
            agent_id="worker_a",
            node_id="a_stale_write",
            resource_key=(state["resource_key"]),
        )

        if conflict is None:
            raise RuntimeError("Conflict not found.")

        await recovery_repository.save_recovery_plan(
            conflict_id=(conflict["_id"]),
            affected_nodes=affected,
            preserved_nodes=preserved,
            strategy=strategy,
        )

        logger.info(
            ("RECOVERY PLAN " "strategy=%s " "affected=%s " "preserved=%s"),
            strategy,
            affected,
            preserved,
        )

        return {
            "affected_nodes": affected,
            "preserved_nodes": preserved,
            "recovery_strategy": strategy,
        }

    # =====================================================
    # ROUTER
    # =====================================================

    def recovery_router(
        state: Phase4State,
    ) -> str:

        if state["recovery_strategy"] == "rebase":
            return "rebase_a"

        return "recover_a_read"

    # =====================================================
    # NON-DISRUPTIVE PATH
    # =====================================================

    async def rebase_a(
        state: Phase4State,
    ) -> dict:

        logger.info("Executing non-disruptive rebase")

        result = await recovery_service.rebase_non_disruptive(
            run_id=state["run_id"],
            resource_key=(state["resource_key"]),
        )

        return {"recovery_result": result}

    # =====================================================
    # DISRUPTIVE SELECTIVE RERUN
    # =====================================================

    async def recover_a_read(
        state: Phase4State,
    ) -> dict:
        """
        Re-execute only A's shared-state read using the
        latest version.

        Worker B is not called again.
        """

        logger.info("Selective recovery: A re-read")

        async with traced_mcp_client(
            run_id=state["run_id"],
            agent_id="worker_a",
            node_id="recover_a_read",
        ) as client:

            result = await client.call_tool(
                "read_shared_resource",
                {"resource_key": state["resource_key"]},
            )

            data = extract_tool_data(result)

        if data.get("status") != "ok":
            raise RuntimeError("Recovery read failed.")

        return {
            "recovery_current_value": data["value"],
            "recovery_current_version": data["version"],
        }

    async def recover_a_reason(
        state: Phase4State,
    ) -> dict:
        """
        Re-execute A's reasoning using ONLY fresh state.
        """

        logger.info("Selective recovery: A reasoning")

        decision = await recovery_planner.plan(
            worker_purpose=(state["a_task_purpose"]),
            current_state=(state["recovery_current_value"]),
        )

        return {"recovery_decision": decision.model_dump()}

    async def recover_a_commit(
        state: Phase4State,
    ) -> dict:
        """
        Commit only the selectively re-executed A branch.
        """

        decision = state["recovery_decision"]

        conflict = await recovery_repository.get_latest_conflict(
            run_id=state["run_id"],
            agent_id="worker_a",
            node_id="a_stale_write",
            resource_key=(state["resource_key"]),
        )

        if conflict is None:
            raise RuntimeError("Conflict not found.")

        # ---------------------------------------------
        # Recovery determines operation is impossible.
        # ---------------------------------------------

        if decision["action"] == "stop":

            result = {
                "status": "stopped",
                "reason": decision["reason"],
            }

            await recovery_repository.save_recovery_result(
                conflict_id=(conflict["_id"]),
                status="stopped",
                result=result,
            )

            return {"recovery_result": result}

        new_value = decision.get("new_value")

        if new_value is None:
            raise RuntimeError("Recovery action=write " "without new_value.")

        # ---------------------------------------------
        # Commit A using the fresh version.
        # ---------------------------------------------

        async with traced_mcp_client(
            run_id=state["run_id"],
            agent_id="worker_a",
            node_id="recover_a_commit",
        ) as client:

            tool_result = await client.call_tool(
                "write_shared_resource",
                {
                    "resource_key": state["resource_key"],
                    "new_value": new_value,
                    "expected_version": state["recovery_current_version"],
                },
            )

            data = extract_tool_data(tool_result)

        await recovery_repository.save_recovery_result(
            conflict_id=(conflict["_id"]),
            status=("completed" if data.get("status") == "ok" else "failed"),
            result=data,
        )

        return {"recovery_result": data}

    # =====================================================
    # VERIFY
    # =====================================================

    async def verify(
        state: Phase4State,
    ) -> dict:

        async with traced_mcp_client(
            run_id=state["run_id"],
            agent_id="verifier",
            node_id="verify",
        ) as client:

            result = await client.call_tool(
                "read_shared_resource",
                {"resource_key": state["resource_key"]},
            )

            data = extract_tool_data(result)

        return {
            "verification": json.dumps(
                data,
                indent=2,
            )
        }

    # =====================================================
    # GRAPH CONSTRUCTION
    # =====================================================

    builder = StateGraph(Phase4State)

    builder.add_node(
        "a_read",
        a_read,
    )

    builder.add_node(
        "b_read",
        b_read,
    )

    builder.add_node(
        "b_write",
        b_write,
    )

    builder.add_node(
        "a_stale_write",
        a_stale_write,
    )

    builder.add_node(
        "semantic_audit",
        semantic_audit,
    )

    builder.add_node(
        "dependency_scan",
        dependency_scan,
    )

    builder.add_node(
        "rebase_a",
        rebase_a,
    )

    builder.add_node(
        "recover_a_read",
        recover_a_read,
    )

    builder.add_node(
        "recover_a_reason",
        recover_a_reason,
    )

    builder.add_node(
        "recover_a_commit",
        recover_a_commit,
    )

    builder.add_node(
        "verify",
        verify,
    )

    # -------------------------------------------------
    # Original execution
    # -------------------------------------------------

    builder.add_edge(
        START,
        "a_read",
    )

    builder.add_edge(
        START,
        "b_read",
    )

    builder.add_edge(
        [
            "a_read",
            "b_read",
        ],
        "b_write",
    )

    builder.add_edge(
        "b_write",
        "a_stale_write",
    )

    builder.add_edge(
        "a_stale_write",
        "semantic_audit",
    )

    builder.add_edge(
        "semantic_audit",
        "dependency_scan",
    )

    # -------------------------------------------------
    # Recovery decision
    # -------------------------------------------------

    builder.add_conditional_edges(
        "dependency_scan",
        recovery_router,
        {
            "rebase_a": "rebase_a",
            "recover_a_read": "recover_a_read",
        },
    )

    # -------------------------------------------------
    # Benign recovery path
    # -------------------------------------------------

    builder.add_edge(
        "rebase_a",
        "verify",
    )

    # -------------------------------------------------
    # Disruptive selective-reexecution subgraph
    # -------------------------------------------------

    builder.add_edge(
        "recover_a_read",
        "recover_a_reason",
    )

    builder.add_edge(
        "recover_a_reason",
        "recover_a_commit",
    )

    builder.add_edge(
        "recover_a_commit",
        "verify",
    )

    builder.add_edge(
        "verify",
        END,
    )

    # -------------------------------------------------
    # Checkpointing
    # -------------------------------------------------

    checkpointer = InMemorySaver()

    return builder.compile(checkpointer=checkpointer)
