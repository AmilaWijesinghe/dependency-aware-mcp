import logging

from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from app.agents.workers import (
    create_worker,
)
from app.graph.state import Phase1State
from app.mcp_client.traced_tools import (
    traced_mcp_tools,
)

logger = logging.getLogger(__name__)


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
    state: Phase1State,
    agent_id: str,
    node_id: str,
    prompt: str,
) -> str:
    """
    Invoke one Deep Agent with an MCP connection carrying
    run/agent/node trace metadata.
    """

    async with traced_mcp_tools(
        run_id=state["run_id"],
        agent_id=agent_id,
        node_id=node_id,
    ) as tools:

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

        return final_text(result)


def build_phase2_graph():

    # -----------------------------------------------------
    # A READ
    # -----------------------------------------------------

    async def a_read(
        state: Phase1State,
    ) -> dict:

        logger.info("Node a_read started")

        text = await invoke_worker(
            state=state,
            agent_id="worker_a",
            node_id="a_read",
            prompt=f"""
Use read_shared_resource to read:

{state["resource_key"]}

Do not modify anything.

Report the value and version.
""",
        )

        return {"worker_a_read": text}

    # -----------------------------------------------------
    # B READ
    # -----------------------------------------------------

    async def b_read(
        state: Phase1State,
    ) -> dict:

        logger.info("Node b_read started")

        text = await invoke_worker(
            state=state,
            agent_id="worker_b",
            node_id="b_read",
            prompt=f"""
Use read_shared_resource to read:

{state["resource_key"]}

Do not modify anything.

Report the value and version.
""",
        )

        return {"worker_b_read": text}

    # -----------------------------------------------------
    # B WRITE
    # -----------------------------------------------------

    async def b_write(
        state: Phase1State,
    ) -> dict:

        logger.info("Node b_write started")

        text = await invoke_worker(
            state=state,
            agent_id="worker_b",
            node_id="b_write",
            prompt=f"""
Use write_shared_resource directly.

Do NOT read first.

Resource:

{state["resource_key"]}

Use:

expected_version={state["initial_version"]}

Write this complete value:

quantity = 60
price = {state["initial_price"]}
description = "{state["initial_description"]}"

Stop after the write result.
""",
        )

        return {"worker_b_write": text}

    # -----------------------------------------------------
    # A STALE WRITE
    # -----------------------------------------------------

    async def a_stale_write(
        state: Phase1State,
    ) -> dict:

        logger.info("Node a_stale_write started")

        text = await invoke_worker(
            state=state,
            agent_id="worker_a",
            node_id="a_stale_write",
            prompt=f"""
Continue using the OLD snapshot from the beginning
of this experiment.

Do NOT read the resource again.

Use write_shared_resource directly.

Resource:

{state["resource_key"]}

Use:

expected_version={state["initial_version"]}

Attempt to write:

quantity = {state["initial_quantity"]}
price = 25
description = "{state["initial_description"]}"

This is intentionally a stale write.

If you receive status='conflict':

STOP immediately.

Do not retry.

Report expected_version and current_version.
""",
        )

        return {"worker_a_stale_write": text}

    # -----------------------------------------------------
    # VERIFY
    # -----------------------------------------------------

    async def verify(
        state: Phase1State,
    ) -> dict:

        text = await invoke_worker(
            state=state,
            agent_id="verifier",
            node_id="verify",
            prompt=f"""
Use read_shared_resource to read:

{state["resource_key"]}

Do not modify anything.

Report the final value and version.
""",
        )

        return {"verification": text}

    # -----------------------------------------------------
    # GRAPH
    # -----------------------------------------------------

    builder = StateGraph(Phase1State)

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
        "verify",
        verify,
    )

    # Parallel initial reads
    builder.add_edge(
        START,
        "a_read",
    )

    builder.add_edge(
        START,
        "b_read",
    )

    # Join
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
        "verify",
    )

    builder.add_edge(
        "verify",
        END,
    )

    return builder.compile()
