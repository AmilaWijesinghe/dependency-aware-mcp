"""Shared resource representation used by storage and MCP."""

from pydantic import BaseModel, Field, JsonValue


class SharedResource(BaseModel):
    resource_key: str = Field(min_length=1)
    value: dict[str, JsonValue]
    version: int = Field(ge=1)
    updated_at: str | None = None
