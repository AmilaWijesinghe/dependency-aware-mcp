"""Exercise baseline response handling with the real MCP SDK and client."""

import asyncio
import unittest
from contextlib import asynccontextmanager
from contextvars import ContextVar
from unittest.mock import patch

from fastmcp import Client
from mcp.server import MCPServer

from app.protocols import baselines
from app.evaluation.scenarios import SCENARIOS, apply_operation
from app.evaluation.schemas import TokenUsage, WorkerDecision, WorkerPreparation


class ProtocolBaselineTests(unittest.IsolatedAsyncioTestCase):
    async def run_protocol(self, protocol, scenario, *, delay_b_lock=False):
        server = MCPServer("baseline-test")
        value = scenario.initial_value.copy()
        version = 1
        owner = None

        @server.tool()
        def read_shared_resource(resource_key: str) -> dict:
            return {"status": "ok", "value": value.copy(), "version": version}

        def commit(new_value):
            nonlocal value, version
            value = new_value.copy()
            version += 1
            return {"status": "ok", "value": value.copy(), "version": version}

        @server.tool()
        def naive_write_shared_resource(resource_key: str, new_value: dict) -> dict:
            return commit(new_value)

        @server.tool()
        def write_shared_resource(
            resource_key: str, new_value: dict, expected_version: int,
        ) -> dict:
            if expected_version != version:
                return {"status": "conflict", "current_version": version}
            return commit(new_value)

        # Each session represents a worker transaction. Context variables carry
        # its identity without adding research metadata to the tool arguments.
        agent = ContextVar("agent")

        @server.tool()
        def acquire_resource_lock(resource_key: str, lease_seconds: int) -> dict:
            nonlocal owner
            if owner is not None:
                return {"status": "busy"}
            owner = agent.get()
            return {"status": "acquired"}

        @server.tool()
        def release_resource_lock(resource_key: str) -> dict:
            nonlocal owner
            self.assertEqual(owner, agent.get())
            owner = None
            return {"status": "released"}

        @server.tool()
        def locked_write_shared_resource(resource_key: str, new_value: dict) -> dict:
            self.assertEqual(owner, agent.get())
            return commit(new_value)

        @asynccontextmanager
        async def connect(*, run_id, agent_id, node_id):
            if delay_b_lock and node_id == "b_lock":
                await asyncio.sleep(0.1)
            token = agent.set(agent_id)
            try:
                async with Client(server) as client:
                    yield client
            finally:
                agent.reset(token)

        class TestWorker:
            """Isolate protocol tests from model calls; never used in benchmarks."""

            def __init__(self, name):
                self.name = name

            async def prepare(self, *, task):
                return WorkerPreparation(
                    task_summary=task, required_fields=[], reasoning_plan=[],
                ), TokenUsage()

            async def decide(self, *, task, preparation, current_state):
                operation = (
                    scenario.worker_a_operation if self.name == "worker_a"
                    else scenario.worker_b_operation
                )
                return WorkerDecision(
                    action="write", new_value=apply_operation(current_state, operation),
                    reason="Protocol test", confidence=1.0,
                ), TokenUsage()

        with (
            patch.object(baselines, "traced_mcp_client", connect),
            patch.object(baselines, "BenchmarkWorker", TestWorker),
        ):
            return await asyncio.wait_for(
                protocol(run_id="baseline-test", scenario=scenario), timeout=10,
            )

    async def test_naive_completes_and_demonstrates_lost_update(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.scenario_id):
                result = await self.run_protocol(baselines.run_naive, scenario)
                self.assertFalse(result.correct)
                self.assertEqual(result.final_value, apply_operation(
                    scenario.initial_value, scenario.worker_a_operation,
                ))
                self.assertEqual(result.final_version, 3)

    async def test_2pl_decodes_lock_acquisition_and_preserves_updates(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.scenario_id):
                result = await self.run_protocol(baselines.run_2pl, scenario)
                self.assertTrue(result.correct)
                self.assertEqual(result.final_value, scenario.expected_final)
                self.assertEqual(result.final_version, 3)

    async def test_occ_decodes_conflict_and_restarts(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.scenario_id):
                result = await self.run_protocol(baselines.run_occ_full_restart, scenario)
                self.assertTrue(result.correct)
                self.assertEqual(result.final_value, scenario.expected_final)
                self.assertEqual(result.final_version, 3)
                self.assertEqual(result.conflicts, 1)
                self.assertEqual(result.retries, 1)

    async def test_2pl_keeps_b_first_when_its_connection_is_delayed(self):
        scenario = next(s for s in SCENARIOS if s.scenario_id == "disruptive_inventory")
        result = await self.run_protocol(baselines.run_2pl, scenario, delay_b_lock=True)
        self.assertTrue(result.correct)
        self.assertEqual(result.final_value, scenario.expected_final)


if __name__ == "__main__":
    unittest.main()
