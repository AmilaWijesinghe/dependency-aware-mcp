from typing import Any

from app.agents.auditor import (
    SemanticAuditor,
)
from app.schemas.conflict import (
    SemanticConflictDecision,
)
from app.storage.repositories import (
    SemanticAuditRepository,
)


def calculate_diff(
    old: dict[str, Any],
    new: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """
    Calculate field-level differences between two
    resource snapshots.
    """

    differences = {}

    keys = set(old) | set(new)

    for key in keys:

        old_value = old.get(key)

        new_value = new.get(key)

        if old_value != new_value:
            differences[key] = {
                "old": old_value,
                "new": new_value,
            }

    return differences


class SemanticAuditorService:

    def __init__(self) -> None:
        self.repository = SemanticAuditRepository()

        self.auditor = SemanticAuditor()

    async def audit_conflict(
        self,
        *,
        run_id: str,
        agent_id: str,
        node_id: str,
        resource_key: str,
    ) -> SemanticConflictDecision:

        # ---------------------------------------------
        # 1. Load structural conflict
        # ---------------------------------------------

        conflict = await self.repository.get_latest_conflict(
            run_id=run_id,
            agent_id=agent_id,
            node_id=node_id,
            resource_key=resource_key,
        )

        if conflict is None:
            raise RuntimeError("No conflict record found for audit.")

        # ---------------------------------------------
        # 2. Find the stale read dependency
        # ---------------------------------------------

        dependency = await self.repository.get_latest_dependency_before_conflict(
            run_id=run_id,
            agent_id=agent_id,
            resource_key=resource_key,
            before=conflict["timestamp"],
        )

        if dependency is None:
            raise RuntimeError(
                "No dependency record found for " "the conflicting agent/resource."
            )

        # ---------------------------------------------
        # 3. Load purpose of affected node
        # ---------------------------------------------

        execution = await self.repository.get_latest_node_execution(
            run_id=run_id,
            agent_id=agent_id,
            node_id=node_id,
        )

        if execution is None:
            raise RuntimeError(
                "No node execution context found " "for Semantic Auditor."
            )

        old_state = dependency["readValue"]

        current_state = conflict["currentValue"]

        attempted_state = conflict["attemptedValue"]

        # ---------------------------------------------
        # 4. Deterministic field-level diff
        # ---------------------------------------------

        changed_fields = calculate_diff(
            old_state,
            current_state,
        )

        intended_changes = calculate_diff(
            old_state,
            attempted_state,
        )

        # ---------------------------------------------
        # 5. Semantic decision
        # ---------------------------------------------

        decision = await self.auditor.classify(
            worker_purpose=execution["purpose"],
            old_state=old_state,
            current_state=current_state,
            attempted_state=attempted_state,
            changed_fields=changed_fields,
            intended_changes=intended_changes,
        )

        # ---------------------------------------------
        # 6. Persist Auditor result
        # ---------------------------------------------

        await self.repository.save_semantic_decision(
            conflict_id=conflict["_id"],
            semantic_result=(decision.semantic_result),
            confidence=(decision.confidence),
            affected_premises=(decision.affected_premises),
            reason=(decision.reason),
            changed_fields=(changed_fields),
            intended_changes=(intended_changes),
            auditor_model=(self.auditor.model_name),
        )

        return decision
