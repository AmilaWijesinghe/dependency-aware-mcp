from deepagents import create_deep_agent
from langchain_ollama import ChatOllama

from app.config import settings

WORKER_SYSTEM_PROMPT = """
You are a worker in a multi-agent shared-state
research experiment.

Rules:

1. Shared state must only be accessed through the
   provided MCP tools.

2. Never invent resource values.

3. Never invent resource versions.

4. If instructed to use an expected_version, use
   exactly that version.

5. If a write reports status='conflict', stop.

6. Never retry a conflicting write unless explicitly
   instructed by the orchestration layer.

7. Do not bypass MCP.
"""


def create_worker(
    *,
    name: str,
    tools,
):
    """
    Create an independent Ollama-powered Deep Agent.
    """

    model = ChatOllama(
        model=settings.ollama_model,
        base_url=(settings.ollama_base_url),
        temperature=0,
    )

    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=(WORKER_SYSTEM_PROMPT),
        name=name,
    )
