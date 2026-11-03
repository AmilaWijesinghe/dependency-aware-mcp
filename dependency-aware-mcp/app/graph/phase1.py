import logging

from langgraph.graph import END, START, StateGraph

from app.graph.state import Phase1State

logger = logging.getLogger(__name__)


def _final_text(result: dict) -> str:
    """
    Get the final textual response from a Deep Agent result.
    """

    messages = result.get("messages", [])

    if not messages:
        return ""

    content = messages[-1].content

    if isinstance(content, str):
        return content

    return str(content)


def build_phase1_graph(worker_a, worker_b):
    """
    Phase 1 experiment:

    1. Worker A and Worker B read the same resource in parallel.
    2. Worker B updates the resource using version 1.
    3. Worker A attempts a write using stale version 1.
    4. Worker B reads the final state for verification.
    """

    # ---------------------------------------------------------
    # Node 1A — Worker A reads initial state
    # ---------------------------------------------------------

    async def worker_a_read_node(
        state: Phase1State,
    ) -> dict:

        logger.info("Worker A initial read started")

        prompt = f"""
Use read_shared_resource to read:

{state["resource_key"]}

Do not modify anything.

Report:
- quantity
- price
- description
- resource version

Use the MCP tool. Do not guess.
"""

        result = await worker_a.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ]
            }
        )

        text = _final_text(result)

        logger.info("Worker A initial read completed")

        return {"worker_a_read": text}

    # ---------------------------------------------------------
    # Node 1B — Worker B reads initial state
    # ---------------------------------------------------------

    async def worker_b_read_node(
        state: Phase1State,
    ) -> dict:

        logger.info("Worker B initial read started")

        prompt = f"""
Use read_shared_resource to read:

{state["resource_key"]}

Do not modify anything.

Report:
- quantity
- price
- description
- resource version

Use the MCP tool. Do not guess.
"""

        result = await worker_b.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ]
            }
        )

        text = _final_text(result)

        logger.info("Worker B initial read completed")

        return {"worker_b_read": text}

    # ---------------------------------------------------------
    # Node 2 — Worker B commits first
    # ---------------------------------------------------------

    async def worker_b_write_node(
        state: Phase1State,
    ) -> dict:

        logger.info("Worker B write started")

        prompt = f"""
Earlier in this controlled experiment you observed this
shared resource snapshot:

resource_key:
{state["resource_key"]}

quantity:
{state["initial_quantity"]}

price:
{state["initial_price"]}

description:
{state["initial_description"]}

version:
{state["initial_version"]}

Now change ONLY quantity from:

{state["initial_quantity"]}

to:

60

Use write_shared_resource directly.

Use:

expected_version={state["initial_version"]}

The complete new value must be:

quantity = 60
price = {state["initial_price"]}
description = "{state["initial_description"]}"

Do NOT read the resource again before writing.

After the write result is returned, stop and report the
result.

If there is a version conflict, do not retry.
"""

        result = await worker_b.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ]
            }
        )

        text = _final_text(result)

        logger.info("Worker B write completed")

        return {"worker_b_write": text}

    # ---------------------------------------------------------
    # Node 3 — Worker A uses stale snapshot
    # ---------------------------------------------------------

    async def worker_a_stale_write_node(
        state: Phase1State,
    ) -> dict:

        logger.info("Worker A stale write started")

        prompt = f"""
You previously observed this shared resource snapshot:

resource_key:
{state["resource_key"]}

quantity:
{state["initial_quantity"]}

price:
{state["initial_price"]}

description:
{state["initial_description"]}

version:
{state["initial_version"]}

Continue using that previously observed snapshot.

Attempt to change ONLY the price from:

{state["initial_price"]}

to:

25

Use write_shared_resource directly with:

expected_version={state["initial_version"]}

Because you are acting from your earlier snapshot, send the
complete value you previously knew, changing only price:

quantity = {state["initial_quantity"]}
price = 25
description = "{state["initial_description"]}"

IMPORTANT:

Do NOT call read_shared_resource before this write.

You are intentionally testing what happens when an agent
acts using stale context.

If write_shared_resource returns a conflict:

- STOP immediately.
- Do NOT retry.
- Do NOT read again.
- Report the expected_version and current_version.
"""

        result = await worker_a.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ]
            }
        )

        text = _final_text(result)

        logger.info("Worker A stale write completed")

        return {"worker_a_stale_write": text}

    # ---------------------------------------------------------
    # Node 4 — Verify final resource
    # ---------------------------------------------------------

    async def verify_node(
        state: Phase1State,
    ) -> dict:

        logger.info("Final verification started")

        prompt = f"""
Read the current value of:

{state["resource_key"]}

using read_shared_resource.

Do not modify anything.

Report:
- quantity
- price
- description
- current version
"""

        result = await worker_b.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ]
            }
        )

        text = _final_text(result)

        logger.info("Final verification completed")

        return {"verification": text}

    # ---------------------------------------------------------
    # Construct graph
    # ---------------------------------------------------------

    builder = StateGraph(Phase1State)

    builder.add_node(
        "worker_a_read",
        worker_a_read_node,
    )

    builder.add_node(
        "worker_b_read",
        worker_b_read_node,
    )

    builder.add_node(
        "worker_b_write",
        worker_b_write_node,
    )

    builder.add_node(
        "worker_a_stale_write",
        worker_a_stale_write_node,
    )

    builder.add_node(
        "verify",
        verify_node,
    )

    # A and B read in parallel
    builder.add_edge(
        START,
        "worker_a_read",
    )

    builder.add_edge(
        START,
        "worker_b_read",
    )

    # Continue only when BOTH initial reads are complete
    builder.add_edge(
        [
            "worker_a_read",
            "worker_b_read",
        ],
        "worker_b_write",
    )

    # B writes first
    builder.add_edge(
        "worker_b_write",
        "worker_a_stale_write",
    )

    # Then A attempts its stale write
    builder.add_edge(
        "worker_a_stale_write",
        "verify",
    )

    builder.add_edge(
        "verify",
        END,
    )

    return builder.compile()
