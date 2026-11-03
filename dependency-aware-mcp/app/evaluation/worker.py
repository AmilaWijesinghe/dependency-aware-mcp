import json

from langchain_ollama import ChatOllama

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


class BenchmarkWorker:
    """
    Controlled LLM worker used by every benchmark protocol.

    The same model and prompts are used across all four
    concurrency strategies.
    """

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
You are Worker {self.name}.

Analyze the following task before reading the
shared resource.

Do not assume any resource values.

TASK:

{task}

Return:
- short task summary
- fields required to complete the task
- concise reasoning plan
""")

        parsed = result.get("parsed")

        if parsed is None:
            raise RuntimeError("Worker preparation parsing failed.")

        usage = extract_usage(result["raw"])

        return parsed, usage

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
You are Worker {self.name}.

TASK:

{task}

PREPARATION:

{preparation.model_dump_json(indent=2)}

CURRENT SHARED RESOURCE:

{json.dumps(current_state, indent=2)}

Rules:

1. Use ONLY the current resource state above.

2. Preserve every field that the task does not
   require you to change.

3. If the task can be completed, return
   action="write" and provide the COMPLETE resource
   value.

4. If the task cannot be completed safely, return
   action="stop".

5. Never invent fields.

Return the structured decision.
""")

        parsed = result.get("parsed")

        if parsed is None:
            raise RuntimeError("Worker decision parsing failed.")

        usage = extract_usage(result["raw"])

        return parsed, usage
