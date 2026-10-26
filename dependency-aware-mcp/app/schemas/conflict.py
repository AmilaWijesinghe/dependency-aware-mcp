"""Structured structural conflict response; no semantic classification yet."""

from typing import Literal

from pydantic import BaseModel


class ConflictResult(BaseModel):
    status: Literal["conflict"] = "conflict"
    resource_key: str
    expected_version: int
    current_version: int | None
