"""Infrastructure checks for one isolated benchmark execution."""

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone

from app.storage.mongodb import resources


_observed = ContextVar("benchmark_resource_versions", default=None)


def execution_resource_key(benchmark_id: str, run_id: str) -> str:
    return f"benchmark/{benchmark_id}/{run_id}/product_1"


@contextmanager
def monitor_resource(resource_key: str):
    token = _observed.set({"key": resource_key, "version": 1})
    try:
        yield
    finally:
        _observed.reset(token)


def check_resource_response(data: dict, resource_key: str) -> dict:
    if data.get("resource_key") != resource_key:
        raise RuntimeError(f"Cross-resource response: expected {resource_key}, got {data}")
    observed = _observed.get()
    if observed is not None and observed["key"] != resource_key:
        raise RuntimeError(f"Cross-execution access: {resource_key}")
    version = data.get("version", data.get("current_version"))
    if version is not None:
        minimum = observed["version"] if observed is not None else 1
        if version < minimum:
            raise RuntimeError(f"Version rollback for {resource_key}: {minimum} -> {version}")
        previous = data.get("previous_version")
        if previous is not None and version != previous + 1:
            raise RuntimeError(f"Invalid version increment for {resource_key}: {data}")
        if observed is not None:
            observed["version"] = version
    return data


async def initialize_resource(*, resource_key: str, initial_value: dict) -> None:
    now = datetime.now(timezone.utc)
    # Insert only: a duplicate identity must fail, never reset a live resource.
    await resources.insert_one({
        "_id": resource_key, "value": deepcopy(initial_value), "version": 1,
        "createdAt": now, "updatedAt": now,
    })
    initial = await resources.find_one({"_id": resource_key})
    if initial is None or initial["version"] != 1 or initial["value"] != initial_value:
        raise RuntimeError(f"Resource initialization failed: {resource_key}")
