import json
import logging

from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from app.agents.workers import (
    create_worker,
)
from app.concurrency.auditor_service import (
    SemanticAuditorService,
)
from app.graph.state import (
    Phase3State,
)
from app.mcp_client.traced_tools import (
    traced_mcp_tools,
)
from app.storage.repositories import (
    NodeExecutionRepository,
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

    if isinstance(content, str):
        return content

    return str(content)


async def invoke_worker(
    *,
    state: Phase3State,
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

            # Restrict tools for experimental control.
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
            execution_id=execution_id,
            error=str(exc),
        )

        raise


def build_phase3_graph():

    auditor_service = SemanticAuditorService()

    # -----------------------------------------------------
    # A READ
    # -----------------------------------------------------

    async def a_read(
        state: Phase3State,
    ) -> dict:

        purpose = "Read the initial shared resource snapshot " "for Worker A."

        prompt = f"""
Use read_shared_resource to read:

{state["resource_key"]}

Do not modify anything.

Report the full value and version.
"""

        text = await invoke_worker(
            state=state,
            agent_id="worker_a",
            node_id="a_read",
            purpose=purpose,
            prompt=prompt,
            allowed_tools={"read_shared_resource"},
        )

        return {"worker_a_read": text}

    # -----------------------------------------------------
    # B READ
    # -----------------------------------------------------

    async def b_read(
        state: Phase3State,
    ) -> dict:

        purpose = "Read the initial shared resource snapshot " "for Worker B."

        prompt = f"""
Use read_shared_resource to read:

{state["resource_key"]}

Do not modify anything.

Report the full value and version.
"""

        text = await invoke_worker(
            state=state,
            agent_id="worker_b",
            node_id="b_read",
            purpose=purpose,
            prompt=prompt,
            allowed_tools={"read_shared_resource"},
        )

        return {"worker_b_read": text}

    # -----------------------------------------------------
    # B WRITE
    # -----------------------------------------------------

    async def b_write(
        state: Phase3State,
    ) -> dict:

        value_json = json.dumps(
            state["b_write_value"],
            indent=2,
        )

        purpose = "Worker B updates the shared resource " "before Worker A commits."

        prompt = f"""
Use write_shared_resource directly.

Do not read first.

Resource:
{state["resource_key"]}

expected_version:
{state["initial_version"]}

Write this complete value:

{value_json}

Stop after the write result.
"""

        text = await invoke_worker(
            state=state,
            agent_id="worker_b",
            node_id="b_write",
            purpose=purpose,
            prompt=prompt,
            allowed_tools={"write_shared_resource"},
        )

        return {"worker_b_write": text}

    # -----------------------------------------------------
    # A STALE WRITE
    # -----------------------------------------------------

    async def a_stale_write(
        state: Phase3State,
    ) -> dict:

        value_json = json.dumps(
            state["a_stale_write_value"],
            indent=2,
        )

        purpose = state["a_task_purpose"]

        prompt = f"""
You are continuing from your OLD resource snapshot.

Do NOT read the resource again.

Your task is:

{purpose}

Use write_shared_resource directly.

Resource:
{state["resource_key"]}

expected_version:
{state["initial_version"]}

Attempt this complete value:

{value_json}

If the write reports a conflict:

STOP immediately.

Do not retry.
"""

        text = await invoke_worker(
            state=state,
            agent_id="worker_a",
            node_id="a_stale_write",
            purpose=purpose,
            prompt=prompt,
            allowed_tools={"write_shared_resource"},
        )

        return {"worker_a_stale_write": text}

    # -----------------------------------------------------
    # SEMANTIC AUDIT
    # -----------------------------------------------------

    async def semantic_audit(
        state: Phase3State,
    ) -> dict:

        logger.info("Semantic Auditor started")

        decision = await auditor_service.audit_conflict(
            run_id=state["run_id"],
            agent_id="worker_a",
            node_id="a_stale_write",
            resource_key=(state["resource_key"]),
        )

        logger.info(
            "Semantic Auditor result=%s confidence=%s",
            decision.semantic_result,
            decision.confidence,
        )

        return {"audit_decision": decision.model_dump()}

    # -----------------------------------------------------
    # VERIFY
    # -----------------------------------------------------

    async def verify(
        state: Phase3State,
    ) -> dict:

        prompt = f"""
Use read_shared_resource to read:

{state["resource_key"]}

Do not modify anything.

Report the final full value and version.
"""

        text = await invoke_worker(
            state=state,
            agent_id="verifier",
            node_id="verify",
            purpose=("Verify final shared resource state."),
            prompt=prompt,
            allowed_tools={"read_shared_resource"},
        )

        return {"verification": text}

    # -----------------------------------------------------
    # GRAPH
    # -----------------------------------------------------

    builder = StateGraph(Phase3State)

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
        "verify",
        verify,
    )

    # Parallel initial reads.
    builder.add_edge(
        START,
        "a_read",
    )

    builder.add_edge(
        START,
        "b_read",
    )

    # Wait for both.
    builder.add_edge(
        [
            "a_read",
            "b_read",
        ],
        "b_write",
    )

    # B changes resource.
    builder.add_edge(
        "b_write",
        "a_stale_write",
    )

    # Structural conflict should now exist.
    builder.add_edge(
        "a_stale_write",
        "semantic_audit",
    )

    # No recovery yet.
    builder.add_edge(
        "semantic_audit",
        "verify",
    )

    builder.add_edge(
        "verify",
        END,
    )

    return builder.compile()
