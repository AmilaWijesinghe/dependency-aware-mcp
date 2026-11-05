import json

from langchain_ollama import (
    ChatOllama,
)

from app.config import settings
from app.schemas.conflict import (
    SemanticConflictDecision,
)


class SemanticAuditor:
    """
    Independent semantic conflict classifier.

    It decides whether a concurrent resource change
    invalidated a premise used by the worker's stale
    reasoning.
    """

    def __init__(
        self,
    ) -> None:

        self.model_name = settings.ollama_auditor_model or settings.ollama_model

        self.model = ChatOllama(
            model=self.model_name,
            base_url=settings.ollama_base_url,
            temperature=0,
        )

        self.structured_model = self.model.with_structured_output(
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

        evidence = {
            "worker_purpose": worker_purpose,
            "old_state": old_state,
            "current_state": current_state,
            "attempted_state": attempted_state,
            "changed_fields": changed_fields,
            "intended_changes": intended_changes,
        }

        result = await self.structured_model.ainvoke(f"""
You are an independent Semantic Conflict Auditor
for a concurrency-control experiment.

Your job is NOT to decide whether a version conflict
exists. A structural version conflict has already been
detected.

Your job is to determine whether the concurrent change
INVALIDATES any premise required to produce the worker's
stale decision.

EVIDENCE:

{json.dumps(evidence, indent=2)}

CLASSIFICATION:

Return exactly one semantic result:

- disruptive
- non_disruptive


GENERAL RULES

1. A version mismatch by itself is NOT enough to call a
   conflict disruptive.

2. Classify NON_DISRUPTIVE only when the worker's exact
   intended result remains valid WITHOUT recomputing its
   state-dependent reasoning.

3. Classify DISRUPTIVE whenever the worker would need to
   recompute its decision using the current state.

4. If the worker purpose explicitly depends on a CURRENT
   field value, that field is a necessary premise.

Examples of dependency language include:

- current quantity
- current price
- current description
- subtract from the current value
- add to the current value
- calculate from the current value
- if current value is above/below a threshold
- only if a current field has a particular value

5. If another worker changed a field used in arithmetic,
   a threshold, a condition, or another calculation, the
   conflict is DISRUPTIVE.

6. A SAME-FIELD conflict is NOT automatically
   non-disruptive.

For example:

old price = 20

worker task:
"reduce CURRENT price by 5"

stale intended price = 15

current price after concurrent update = 12

The worker must recompute:

12 - 5 = 7

Therefore this is DISRUPTIVE.

7. Different-field changes can be NONDISRUPTIVE when the
   worker explicitly says its decision does not depend on
   that changed field.

Example:

worker task:
"set price to 25 independently of quantity"

another worker changes quantity

The exact price=25 decision remains valid.

Therefore this is NONDISRUPTIVE.

8. If a concurrent change causes a condition to become
   false and the worker should now STOP, the conflict is
   DISRUPTIVE.

9. Ask this final question:

"Could the worker safely reuse the exact stale decision
without re-reading or recomputing anything?"

If YES:
    non_disruptive

If NO:
    disruptive


AFFECTED PREMISES

List the specific premises invalidated by the concurrent
change.

If none are invalidated, return an empty list.


CONFIDENCE

Return a confidence from 0.0 to 1.0.


Do not classify based only on field names.

Reason from the worker's stated dependency on the old
resource values.
""")

        parsed = result.get("parsed")

        if parsed is None:

            raw = result.get("raw")

            parsing_error = result.get("parsing_error")

            raw_content = getattr(
                raw,
                "content",
                None,
            )

            raise RuntimeError(
                "Semantic Auditor parsing failed. "
                f"parsing_error="
                f"{parsing_error!r}; "
                f"raw_content="
                f"{raw_content!r}"
            )

        return parsed
