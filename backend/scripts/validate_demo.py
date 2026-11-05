"""Acceptance validation against the REAL running demo API (no substitutes)."""

import argparse
import asyncio
import json

import httpx


async def validate(base_url: str):
    async with httpx.AsyncClient(base_url=base_url, timeout=960, trust_env=False) as client:
        scenarios = await client.get("/api/demo/scenarios")
        scenarios.raise_for_status()
        assert {item["id"] for item in scenarios.json()} == {"non_disruptive", "disruptive"}
        keys = set()
        for scenario, quantity, price, strategy, reruns in [
            ("non_disruptive", 60, 25, "rebase", 0),
            ("disruptive", 30, 20, "selective_reexecution", 3),
        ]:
            response = await client.post("/api/demo/run", json={"scenario": scenario})
            response.raise_for_status()
            run = response.json()
            assert run["resourceKey"] == f"demo/{run['demoId']}/product_1"
            assert run["resourceKey"] not in keys
            keys.add(run["resourceKey"])
            events = []
            async with client.stream("GET", run["eventsUrl"]) as stream:
                stream.raise_for_status()
                assert "text/event-stream" in stream.headers["content-type"]
                async for line in stream.aiter_lines():
                    if line.startswith("data: "):
                        event = json.loads(line[6:])
                        events.append(event)
                        print(f"{scenario}: {event['type']}", flush=True)
            assert events and events[-1]["type"] == "demo_completed", events[-1] if events else "Empty stream"
            data = {event["type"]: event["data"] for event in events}
            assert data["semantic_audit_completed"]["semanticResult"] == scenario
            assert data["recovery_completed"]["strategy"] == strategy
            assert data["recovery_completed"]["nodesReexecuted"] == reruns
            assert data["final_state"]["resource"] == {
                "quantity": quantity, "price": price, "description": "Test Product", "version": 3,
            }
            assert data["metrics"]["conflicts"] == 1
            assert [event["id"] for event in events] == list(range(1, len(events) + 1))
            print(f"PASS: {scenario}; SSE; final state; {run['resourceKey']}", flush=True)
    print("PASS: both live backend scenarios", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    arguments = parser.parse_args()
    try:
        asyncio.run(validate(arguments.base_url))
    except Exception as exc:
        print(f"FAIL: live demo validation ({type(exc).__name__}): {exc}", flush=True)
        raise SystemExit(1)
