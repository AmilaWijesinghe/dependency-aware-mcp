import json

from langchain_ollama import (
    ChatOllama,
)

from app.config import settings
from app.evaluation.schemas import (
    TokenUsage,
    WorkerDecision,
    WorkerPreparation,
)


def extract_usage(
    raw_message,
) -> TokenUsage:

    metadata = getattr(
        raw_message,
        "usage_metadata",
        None,
    )

    if not metadata:
        return TokenUsage()

    return TokenUsage(
        input_tokens=metadata.get(
            "input_tokens",
            0,
        ),
        output_tokens=metadata.get(
            "output_tokens",
            0,
        ),
        total_tokens=metadata.get(
            "total_tokens",
            0,
        ),
    )


def structured_error(
    *,
    label: str,
    result: dict,
) -> RuntimeError:
    """
    Produce a useful error when structured output parsing
    fails.

    include_raw=True returns the original response plus
    parsing information.
    """

    raw = result.get("raw")

    parsing_error = result.get("parsing_error")

    raw_content = getattr(
        raw,
        "content",
        None,
    )

    return RuntimeError(
        f"{label} parsing failed. "
        f"parsing_error="
        f"{parsing_error!r}; "
        f"raw_content="
        f"{raw_content!r}"
    )


class BenchmarkWorker:

    def __init__(
        self,
        name: str,
    ) -> None:

        self.name = name

        self.model = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0,
        )

        self.preparation_model = self.model.with_structured_output(
            WorkerPreparation,
            method="json_schema",
            include_raw=True,
        )

        self.decision_model = self.model.with_structured_output(
            WorkerDecision,
            method="json_schema",
            include_raw=True,
        )

    async def prepare(
        self,
        *,
        task: str,
    ) -> tuple[
        WorkerPreparation,
        TokenUsage,
    ]:

        result = await self.preparation_model.ainvoke(f"""
You are {self.name}, a worker in a controlled
multi-agent concurrency experiment.

Analyze the task BEFORE reading shared state.

TASK:
{task}

Do not invent current resource values.

Return a structured preparation containing:

1. task_summary
2. required_fields
3. reasoning_plan

Keep the plan concise.
""")

        parsed = result.get("parsed")

        if parsed is None:

            raise structured_error(
                label=("Worker preparation"),
                result=result,
            )

        usage = extract_usage(result["raw"])

        return (
            parsed,
            usage,
        )

    async def decide(
        self,
        *,
        task: str,
        preparation: WorkerPreparation,
        current_state: dict,
    ) -> tuple[
        WorkerDecision,
        TokenUsage,
    ]:

        result = await self.decision_model.ainvoke(f"""
You are {self.name}, a worker in a controlled
multi-agent concurrency experiment.

TASK:
{task}

PREPARATION:
{preparation.model_dump_json(indent=2)}

CURRENT SHARED RESOURCE:
{json.dumps(current_state, indent=2)}

IMPORTANT RESOURCE CONTRACT:

The shared resource has EXACTLY these fields:

- quantity
- price
- description

Never rename these fields.

In particular:

- use "description"
- NEVER use "product_description"
- NEVER add new fields
- NEVER remove existing fields

DECISION RULES:

1. Use ONLY the CURRENT SHARED RESOURCE shown above.

2. Re-evaluate every condition using the current values.

3. If the task says CURRENT quantity, CURRENT price,
   CURRENT description, or uses a threshold/calculation,
   compute the answer from the current values shown above.

4. Preserve all fields the task does not change.

5. If the task CAN be completed:

   action = "write"

   new_value must contain the COMPLETE resource with
   exactly:

   {{
       "quantity": ...,
       "price": ...,
       "description": ...
   }}

6. If the task CANNOT be completed because a condition
   fails:

   action = "stop"

   new_value = null

7. For action="stop", do not invent a replacement state.

8. Never use stale values from earlier reasoning.

Return only the required structured decision.
""")

        parsed = result.get("parsed")

        if parsed is None:

            raise structured_error(
                label=("Worker decision"),
                result=result,
            )

        usage = extract_usage(result["raw"])

        return (
            parsed,
            usage,
        )
