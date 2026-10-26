from langchain_core.tools import tool
from langchain_ollama import ChatOllama

from app.config import settings


@tool
def get_test_number() -> int:
    """Return the test number from the system."""
    return 42


model = ChatOllama(
    model=settings.ollama_model,
    base_url=settings.ollama_base_url,
    temperature=0,
)

model_with_tools = model.bind_tools(
    [get_test_number]
)

response = model_with_tools.invoke(
    """
Use the available tool to get the test number.
Do not answer from your own knowledge.
"""
)

print("Content:")
print(response.content)

print("\nTool calls:")
print(response.tool_calls)