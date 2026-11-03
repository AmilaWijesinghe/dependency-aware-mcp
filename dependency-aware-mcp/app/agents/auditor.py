import json

from langchain_ollama import ChatOllama

from app.config import settings
from app.schemas.conflict import (
    SemanticConflictDecision,
)


class SemanticAuditor:
    """
    Independent LLM-powered Semantic Auditor.

    It determines whether a structural resource-version
    conflict actually invalidates the worker's reasoning.
    """

    def __init__(self) -> None:

        auditor_model = settings.ollama_auditor_model or settings.ollama_model

        model = ChatOllama(
            model=auditor_model,
            base_url=settings.ollama_base_url,
            temperature=0,
        )

        self.model_name = auditor_model

        self.structured_model = model.with_structured_output(
            SemanticConflictDecision,
            method="json_schema",
            include_raw=True,
        )

    async def classify(
        self,
        *,
        worker_purpose: str,
        old_state: dict,
        current_state: dict,
        attempted_state: dict,
        changed_fields: dict,
        intended_changes: dict,
    ) -> SemanticConflictDecision:

        prompt = f"""
You are an independent Semantic Conflict Auditor for
a multi-agent concurrency-control system.

A structural resource-version conflict has already
been detected.

IMPORTANT:

A version mismatch by itself does NOT mean the
worker's reasoning is semantically invalid.

Your job is to determine whether the changes to the
shared resource invalidate a factual premise or
assumption that is necessary for the worker's
intended task.

Classify as:

"disruptive"

ONLY when the new resource state invalidates a
premise required to perform the worker's intended
operation correctly.

Classify as:

"non_disruptive"

when the resource changed, but the changed fields do
not affect the worker's intended decision or action.

Example:

If a worker wants to change only product price, and
another agent changed only available quantity, the
version conflict may be NON_DISRUPTIVE if the price
decision does not depend on quantity.

If a worker intends to allocate 50 units because it
believed 100 were available, but another agent
changed available quantity to 40, the change is
DISRUPTIVE because the availability premise is no
longer valid.

Do not classify based on the version number itself.

Evaluate only semantic dependency.

WORKER PURPOSE:
{worker_purpose}

OLD RESOURCE STATE:
{json.dumps(old_state, indent=2)}

CURRENT RESOURCE STATE:
{json.dumps(current_state, indent=2)}

STALE WRITE THE WORKER ATTEMPTED:
{json.dumps(attempted_state, indent=2)}

FIELDS CHANGED BY OTHER WORK:
{json.dumps(changed_fields, indent=2)}

WORKER'S INTENDED CHANGES:
{json.dumps(intended_changes, indent=2)}

Return the required structured decision.
"""

        result = await self.structured_model.ainvoke(prompt)

        parsing_error = result.get("parsing_error")

        if parsing_error is not None:
            raise RuntimeError(
                "Semantic Auditor structured-output " f"parsing failed: {parsing_error}"
            )

        parsed = result.get("parsed")

        if parsed is None:
            raise RuntimeError("Semantic Auditor returned no parsed result.")

        return parsed
