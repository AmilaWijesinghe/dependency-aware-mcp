import json

from langchain_ollama import ChatOllama

from app.config import settings
from app.schemas.recovery import RecoveryDecision


class RecoveryPlanner:
    """
    Recomputes an affected worker operation using fresh state.
    """

    def __init__(self) -> None:

        model_name = settings.ollama_auditor_model or settings.ollama_model

        model = ChatOllama(
            model=model_name,
            base_url=settings.ollama_base_url,
            temperature=0,
        )

        self.structured_model = model.with_structured_output(
            RecoveryDecision,
            method="json_schema",
        )

    async def plan(
        self,
        *,
        worker_purpose: str,
        current_state: dict,
    ) -> RecoveryDecision:

        prompt = f"""
You are selectively re-executing one invalidated
branch of a multi-agent workflow.

The old resource snapshot must NOT be used.

Use ONLY the CURRENT RESOURCE STATE below.

WORKER TASK:

{worker_purpose}

CURRENT RESOURCE STATE:

{json.dumps(current_state, indent=2)}

Rules:

1. Recalculate the requested operation using the
   current state.

2. Preserve every field that the task does not need
   to modify.

3. Never restore an old/stale field value.

4. If the requested operation can still safely be
   completed, return action="write" and provide the
   COMPLETE new resource value.

5. If the operation cannot safely be completed,
   return action="stop" and new_value=null.

Example:

If the task says "allocate 30 units", this means
subtract exactly 30 from the CURRENT quantity.

If current quantity is 60:
new quantity = 30.

If current quantity is 20:
the operation cannot allocate 30 and should stop.

Return only the structured response.
"""

        return await self.structured_model.ainvoke(prompt)
