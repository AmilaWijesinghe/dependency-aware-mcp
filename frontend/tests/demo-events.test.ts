import assert from "node:assert/strict";
import test from "node:test";
import { applyDemoEvent, initialState } from "../lib/demo-events.ts";
import type { DemoEvent } from "../lib/types.ts";

test("replayed SSE events are idempotent and recovery preserves B", () => {
  let state = initialState();
  const event: DemoEvent = { id: 1, timestamp: "2026-11-03T00:00:00Z", type: "resource_write", data: {
    agentId: "worker_b", nodeId: "b_write", resource: { quantity: 60, price: 20, description: "Test Product", version: 2 },
  } };
  state = applyDemoEvent(state, event);
  assert.equal(applyDemoEvent(state, event), state);
  state = applyDemoEvent(state, { id: 2, timestamp: event.timestamp, type: "agent_read", data: {
    agentId: "worker_a", nodeId: "recover_a_read", version: 2, resource: event.data.resource,
  } });
  assert.equal(state.agents.worker_b.status, "completed");
  assert.equal(state.agents.worker_b.writeVersion, 2);
  assert.equal(state.agents.worker_a.readVersion, 2);
});

test("failure stops active workers and clears audit loading", () => {
  let state = { ...initialState(), auditing: true };
  state = applyDemoEvent(state, { id: 1, timestamp: "2026-11-03T00:00:00Z", type: "demo_failed", data: { message: "Safe error" } });
  assert.equal(state.status, "failed");
  assert.equal(state.auditing, false);
  assert.equal(state.agents.worker_a.status, "stopped");
  assert.equal(state.error, "Safe error");
});
