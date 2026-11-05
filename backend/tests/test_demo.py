"""Demo integration tests with isolated persistence and model inference."""

import asyncio
import json
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app.demo.events import DemoRun, DemoStore
from app.demo.service import TokenUsage, execute_demo, short_summary
from app.main import create_app
from demo_support import IsolatedResearchStack

logging.getLogger().setLevel(logging.ERROR)


def decode_sse(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


class DemoIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ready = asyncio.Event()
        self.stop = asyncio.Event()
        async def host_stack():
            # AnyIO cancel scopes must enter and exit in the same task.
            async with IsolatedResearchStack() as stack:
                self.stack = stack
                self.ready.set()
                await self.stop.wait()
        self.stack_task = asyncio.create_task(host_stack())
        await asyncio.wait_for(self.ready.wait(), 5)
        self.store = DemoStore()
        self.app = create_app(demo_store=self.store)
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.store.close()
        await self.http.aclose()
        self.stop.set()
        await self.stack_task

    async def run_scenario(self, scenario):
        response = await self.http.post("/api/demo/run", json={"scenario": scenario})
        self.assertEqual(response.status_code, 202)
        run = response.json()
        self.assertEqual(run["resourceKey"], f"demo/{run['demoId']}/product_1")
        response = await self.http.get(run["eventsUrl"])
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        events = decode_sse(response.text)
        self.assertEqual(events[0]["type"], "demo_started")
        self.assertEqual(events[-1]["type"], "demo_completed", events)
        self.assertEqual([item["id"] for item in events], list(range(1, len(events) + 1)))
        kinds = [event["type"] for event in events]
        for earlier, later in zip([
            "resource_initialized", "agent_read", "conflict_detected", "semantic_audit_started",
            "semantic_audit_completed", "dependency_analysis_completed", "recovery_started",
            "recovery_completed", "final_state", "metrics",
        ], [
            "agent_read", "conflict_detected", "semantic_audit_started", "semantic_audit_completed",
            "dependency_analysis_completed", "recovery_started", "recovery_completed",
            "final_state", "metrics", "demo_completed",
        ]):
            self.assertLess(kinds.index(earlier), kinds.index(later))
        by_type = {event["type"]: event["data"] for event in events}
        self.assertEqual(by_type["semantic_audit_completed"]["semanticResult"], scenario)
        self.assertEqual(by_type["conflict_detected"], {"agentId": "worker_a", "expectedVersion": 1, "actualVersion": 2})
        self.assertEqual([event["data"]["resource"]["version"] for event in events if event["type"] in {"resource_initialized", "resource_write"}], [1, 2, 3])
        self.assertEqual(by_type["metrics"]["conflicts"], 1)
        self.assertEqual(by_type["metrics"]["retries"], 1)
        self.assertIsNone(by_type["metrics"]["totalTokens"])
        self.assertIsNone(by_type["metrics"]["wastedTokens"])
        self.assertNotIn("PRIVATE_MODEL_TEXT", response.text)
        self.assertNotIn('"prompt"', response.text)
        self.assertNotIn('"messages"', response.text)
        reads = [event for event in events if event["type"] == "agent_read" and event["data"]["nodeId"] in {"a_read", "b_read"}]
        self.assertEqual({item["data"]["agentId"] for item in reads}, {"worker_a", "worker_b"})
        self.assertTrue(all(item["data"]["version"] == 1 for item in reads))
        return run, events, by_type

    async def test_non_disruptive_rebase_and_final_state(self):
        _, _, data = await self.run_scenario("non_disruptive")
        self.assertEqual(data["recovery_completed"]["strategy"], "rebase")
        self.assertEqual(data["recovery_completed"]["nodesReexecuted"], 0)
        self.assertEqual(data["recovery_completed"]["nodesPreserved"], 4)
        self.assertEqual(data["recovery_completed"]["affectedNodes"], [])
        self.assertEqual(data["final_state"]["resource"], {"quantity": 60, "price": 25, "description": "Test Product", "version": 3})

    async def test_disruptive_selective_recovery_and_final_state(self):
        _, _, data = await self.run_scenario("disruptive")
        self.assertEqual(data["recovery_completed"]["strategy"], "selective_reexecution")
        self.assertEqual(data["recovery_completed"]["reexecutedNodes"], ["recover_a_read", "recover_a_reason", "recover_a_commit"])
        self.assertEqual(data["recovery_completed"]["preservedNodes"], ["b_read", "b_write"])
        self.assertEqual(data["final_state"]["resource"], {"quantity": 30, "price": 20, "description": "Test Product", "version": 3})

    async def test_concurrent_runs_are_isolated(self):
        first, second = await asyncio.gather(self.run_scenario("non_disruptive"), self.run_scenario("disruptive"))
        self.assertNotEqual(first[0]["resourceKey"], second[0]["resourceKey"])
        documents = self.stack.collections["resources"].documents
        self.assertEqual(len(documents), 2)
        for collection in self.stack.collections.values():
            for document in collection.documents:
                if "resourceKey" in document:
                    self.assertEqual(document["resourceKey"], f"demo/{document['runId']}/product_1")

    async def test_sse_reconnect_replays_only_unseen_events(self):
        run, events, _ = await self.run_scenario("non_disruptive")
        replay = await self.http.get(run["eventsUrl"], headers={"Last-Event-ID": "5"})
        self.assertEqual(decode_sse(replay.text), events[5:])
        replay = await self.http.get(run["eventsUrl"], headers={"Last-Event-ID": str(len(events))})
        self.assertEqual(replay.text, "")
        for value in ["bad", "-1", str(len(events) + 1)]:
            self.assertEqual((await self.http.get(run["eventsUrl"], headers={"Last-Event-ID": value})).status_code, 400)

    async def test_discovery_validation_cors_and_missing_run(self):
        self.assertEqual(len((await self.http.get("/api/demo/scenarios")).json()), 2)
        self.assertEqual((await self.http.post("/api/demo/run", json={"scenario": "heldout"})).status_code, 422)
        self.assertEqual((await self.http.get("/api/demo/events/unknown")).status_code, 404)
        response = await self.http.get("/api/demo/scenarios", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:3000")
        response = await self.http.get("/api/demo/scenarios", headers={"Origin": "https://unrelated.example"})
        self.assertNotIn("access-control-allow-origin", response.headers)

    async def test_backend_failure_is_safe_and_terminal(self):
        with patch("app.demo.service.resources.insert_one", AsyncMock(side_effect=RuntimeError("SECRET_STACK_TRACE"))):
            with self.assertLogs("app.demo.service", level="ERROR"):
                run = (await self.http.post("/api/demo/run", json={"scenario": "disruptive"})).json()
                response = await self.http.get(run["eventsUrl"])
        events = decode_sse(response.text)
        self.assertEqual(events[-1]["type"], "demo_failed")
        self.assertNotIn("SECRET_STACK_TRACE", response.text)
        self.assertNotIn("final_state", [item["type"] for item in events])

    async def test_incorrect_final_state_cannot_complete(self):
        from app.schemas.recovery import RecoveryDecision
        async def wrong_plan(*args, **kwargs):
            return RecoveryDecision(action="write", new_value={"quantity": 70, "price": 20, "description": "Test Product"}, reason="Incorrect test decision", confidence=0.9)
        with patch("app.agents.recovery_planner.RecoveryPlanner.plan", wrong_plan):
            with self.assertLogs("app.demo.service", level="ERROR"):
                run = (await self.http.post("/api/demo/run", json={"scenario": "disruptive"})).json()
                events = decode_sse((await self.http.get(run["eventsUrl"])).text)
        self.assertEqual(events[-1]["type"], "demo_failed")
        self.assertNotIn("final_state", [item["type"] for item in events])


class DemoEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_event_delivery_and_disconnected_observer(self):
        run = DemoRun("test", "disruptive")
        stream = run.stream()
        waiting = asyncio.create_task(anext(stream))
        await run.publish("demo_started", {})
        self.assertIn('"type": "demo_started"', await asyncio.wait_for(waiting, 1))
        await stream.aclose()
        await run.publish("demo_completed", {})
        replay = "".join([chunk async for chunk in run.stream()])
        self.assertEqual(len(decode_sse(replay)), 2)

    async def test_capacity_expiry_and_shutdown(self):
        async def blocked(run):
            await asyncio.Event().wait()
        store = DemoStore(ttl_seconds=-1, max_active=1, runner=blocked)
        run = store.start("disruptive")
        with self.assertRaises(RuntimeError):
            store.start("disruptive")
        await run.publish("demo_completed", {})
        store.prune()
        self.assertNotIn(run.demo_id, store.runs)
        run.task.cancel()
        await asyncio.gather(run.task, return_exceptions=True)
        next_run = store.start("disruptive")
        await store.close()
        self.assertTrue(next_run.task.done())

    async def test_token_measurements_and_summary_redaction(self):
        usage = TokenUsage()
        self.assertIsNone(usage.metrics()["totalTokens"])
        response = SimpleNamespace(generations=[[SimpleNamespace(message=SimpleNamespace(usage_metadata={"input_tokens": 12, "output_tokens": 3}))]])
        await usage.on_llm_end(response)
        self.assertEqual(usage.metrics()["totalTokens"], 15)
        response.generations[0][0].message.usage_metadata = None
        await usage.on_llm_end(response)
        self.assertIsNone(usage.metrics()["totalTokens"])
        partial = TokenUsage()
        response.generations[0][0].message.usage_metadata = {"input_tokens": 12}
        await partial.on_llm_end(response)
        self.assertIsNone(partial.metrics()["totalTokens"])
        self.assertEqual(short_summary("<think>private</think>Safe fact."), "Safe fact.")


if __name__ == "__main__":
    unittest.main()
