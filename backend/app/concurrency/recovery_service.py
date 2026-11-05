from copy import deepcopy

from app.mcp_client.traced_tools import (
    extract_tool_data,
    traced_mcp_client,
)
from app.storage.repositories import (
    RecoveryRepository,
)


class RecoveryService:

    def __init__(self) -> None:
        self.repository = RecoveryRepository()

    async def rebase_non_disruptive(
        self,
        *,
        run_id: str,
        resource_key: str,
    ) -> dict:
        """
        Apply Worker A's non-conflicting intended field
        changes onto the current resource state.

        Phase 4 v1 supports top-level field rebasing.
        """

        conflict = await self.repository.get_latest_conflict(
            run_id=run_id,
            agent_id="worker_a",
            node_id="a_stale_write",
            resource_key=resource_key,
        )

        if conflict is None:
            raise RuntimeError("Conflict not found for recovery.")

        current_value = deepcopy(conflict["currentValue"])

        intended_changes = conflict.get(
            "intendedChanges",
            {},
        )

        # ---------------------------------------------
        # Rebase only A's intended fields onto the
        # latest B-produced state.
        # ---------------------------------------------

        rebased_value = deepcopy(current_value)

        for field, change in intended_changes.items():
            rebased_value[field] = change["new"]

        expected_version = conflict["actualVersion"]

        async with traced_mcp_client(
            run_id=run_id,
            agent_id="worker_a",
            node_id="rebase_a",
        ) as client:

            result = await client.call_tool(
                "write_shared_resource",
                {
                    "resource_key": resource_key,
                    "new_value": rebased_value,
                    "expected_version": expected_version,
                },
            )

            data = extract_tool_data(result)

        await self.repository.save_recovery_result(
            conflict_id=conflict["_id"],
            status=("completed" if data.get("status") == "ok" else "failed"),
            result=data,
        )

        return data
