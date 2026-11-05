"""Bounded, replayable per-run SSE journals for a single local API process."""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4


@dataclass
class DemoRun:
    demo_id: str
    scenario: str
    events: list[dict] = field(default_factory=list)
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task | None = None
    finished_at: float | None = None

    @property
    def resource_key(self) -> str:
        return f"demo/{self.demo_id}/product_1"

    async def publish(self, kind: str, data: dict) -> None:
        async with self.changed:
            self.events.append({
                "id": len(self.events) + 1, "type": kind,
                "timestamp": datetime.now(timezone.utc).isoformat(), "data": data,
            })
            if kind in {"demo_completed", "demo_failed"}:
                self.finished_at = monotonic()
            self.changed.notify_all()

    async def stream(self, after: int = 0):
        cursor = after
        while True:
            async with self.changed:
                if cursor >= len(self.events) and self.finished_at is None:
                    try:
                        await asyncio.wait_for(self.changed.wait(), timeout=15)
                    except TimeoutError:
                        pass
                pending = self.events[cursor:]
                finished = self.finished_at is not None
            for event in pending:
                cursor = event["id"]
                yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
            if finished:
                return
            if not pending:
                yield ": keep-alive\n\n"


class DemoStore:
    def __init__(self, *, ttl_seconds: float = 3600, max_runs: int = 32,
                 max_active: int = 2, runner=None):
        self.runs: dict[str, DemoRun] = {}
        self.ttl_seconds = ttl_seconds
        self.max_runs = max_runs
        self.max_active = max_active
        self.runner = runner

    def prune(self) -> None:
        now = monotonic()
        for key, run in list(self.runs.items()):
            if run.finished_at is not None and now - run.finished_at > self.ttl_seconds:
                del self.runs[key]

    def start(self, scenario: str) -> DemoRun:
        self.prune()
        if sum(run.finished_at is None for run in self.runs.values()) >= self.max_active:
            raise RuntimeError("Two demos are already running. Wait for one to finish.")
        if len(self.runs) >= self.max_runs:
            completed = [run for run in self.runs.values() if run.finished_at is not None]
            if not completed:
                raise RuntimeError("Demo capacity reached. Try again later.")
            oldest = min(completed, key=lambda run: run.finished_at)
            del self.runs[oldest.demo_id]
        run = DemoRun(demo_id=str(uuid4()), scenario=scenario)
        self.runs[run.demo_id] = run
        if self.runner is None:
            from app.demo.service import execute_demo
            runner = execute_demo
        else:
            runner = self.runner
        run.task = asyncio.create_task(runner(run))
        return run

    async def close(self) -> None:
        tasks = [run.task for run in self.runs.values() if run.task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
