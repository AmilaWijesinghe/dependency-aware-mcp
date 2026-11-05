import type { DemoEvent, DemoState, Scenario } from "./types.ts";

export function initialState(scenario?: Scenario): DemoState {
  return {
    status: "idle", events: [], resourceHistory: [], auditing: false, recovered: false,
    agents: {
      worker_a: { agentId: "worker_a", task: scenario?.workerATask ?? "Select a scenario to begin.", status: "idle" },
      worker_b: { agentId: "worker_b", task: scenario?.workerBTask ?? "Select a scenario to begin.", status: "idle" },
    },
  };
}

export function applyDemoEvent(state: DemoState, event: DemoEvent): DemoState {
  if (state.events.some(item => item.id === event.id)) return state;
  const next = { ...state, events: [...state.events, event], agents: { ...state.agents } };
  const updateAgent = (id: "worker_a" | "worker_b", patch: Partial<DemoState["agents"]["worker_a"]>) => {
    next.agents[id] = { ...next.agents[id], ...patch };
  };
  switch (event.type) {
    case "demo_started":
      next.status = "running"; next.resourceKey = event.data.resourceKey;
      updateAgent("worker_a", { task: event.data.workerATask, status: "reading" });
      updateAgent("worker_b", { task: event.data.workerBTask, status: "reading" }); break;
    case "resource_initialized": case "resource_write":
      next.resource = event.data.resource;
      next.resourceHistory = [...state.resourceHistory, event.data.resource];
      if (event.type === "resource_write") updateAgent(event.data.agentId, {
        status: "completed", writeVersion: event.data.resource.version,
      }); break;
    case "agent_read":
      updateAgent(event.data.agentId, { status: "reasoning", readVersion: event.data.version }); break;
    case "agent_decision":
      updateAgent(event.data.agentId, { decision: event.data.summary, status: "writing" }); break;
    case "conflict_detected":
      next.conflict = event.data; updateAgent(event.data.agentId, { status: "conflict" }); break;
    case "semantic_audit_started": next.auditing = true; break;
    case "semantic_audit_completed": next.audit = event.data; next.auditing = false; break;
    case "dependency_analysis_completed": case "recovery_started":
      next.recovery = event.data; break;
    case "recovery_completed": next.recovery = event.data; next.recovered = true; break;
    case "final_state": next.final = event.data.resource; break;
    case "metrics": next.metrics = event.data; break;
    case "demo_completed": next.status = "completed"; break;
    case "demo_failed":
      next.status = "failed"; next.error = event.data.message; next.auditing = false;
      for (const id of ["worker_a", "worker_b"] as const) {
        if (next.agents[id].status !== "completed") updateAgent(id, { status: "stopped" });
      }
      break;
  }
  return next;
}

export function describeEvent(event: DemoEvent): string {
  const worker = (id: string) => id === "worker_a" ? "Worker A" : "Worker B";
  switch (event.type) {
    case "demo_started": return "Isolated execution started";
    case "resource_initialized": return `Shared resource initialized at v${event.data.resource.version}`;
    case "agent_read": return `${worker(event.data.agentId)} read v${event.data.version}${event.data.nodeId.startsWith("recover") ? " · fresh snapshot" : ""}`;
    case "agent_decision": return `${worker(event.data.agentId)} · ${event.data.summary}`;
    case "resource_write": return `${worker(event.data.agentId)} committed v${event.data.resource.version}`;
    case "conflict_detected": return `Worker A expected v${event.data.expectedVersion}; current state is v${event.data.actualVersion}`;
    case "semantic_audit_started": return "Semantic Auditor is checking the changed premises";
    case "semantic_audit_completed": return `Auditor classified the conflict as ${event.data.semanticResult.replaceAll("_", " ")}`;
    case "dependency_analysis_completed": return `${event.data.affectedNodes.length} affected nodes · ${event.data.nodesPreserved} preserved`;
    case "recovery_started": return event.data.strategy === "rebase" ? "Rebasing the valid price decision" : "Re-executing the affected A branch";
    case "recovery_step": return event.data.summary;
    case "recovery_completed": return `Recovery committed · ${event.data.nodesReexecuted} nodes re-executed`;
    case "final_state": return `Final state verified through MCP at v${event.data.resource.version}`;
    case "metrics": return "Measured demo run metrics received";
    case "demo_completed": return "Execution completed successfully";
    case "demo_failed": return event.data.message;
  }
}
