export type ScenarioType = "non_disruptive" | "disruptive";
export type DemoStatus = "idle" | "running" | "completed" | "failed";
export type AgentId = "worker_a" | "worker_b";
export interface Scenario {
  id: ScenarioType; name: string; description: string;
  workerATask: string; workerBTask: string;
}
export interface ResourceState { quantity: number; price: number; description: string; version: number }
export interface AgentState {
  agentId: AgentId; task: string;
  status: "idle" | "reading" | "reasoning" | "writing" | "conflict" | "completed" | "stopped";
  readVersion?: number; decision?: string; writeVersion?: number;
}
export interface AuditResult {
  semanticResult: ScenarioType; affectedPremises: string[]; reason: string; confidence: number;
}
export interface RecoveryResult {
  strategy: "rebase" | "selective_reexecution";
  nodesReexecuted: number; nodesPreserved: number;
  candidateNodes: string[]; affectedNodes: string[]; preservedNodes: string[];
  reexecutedNodes: string[]; edges: { source: string; target: string }[];
}
export interface DemoMetrics {
  elapsedMs: number; inputTokens: number | null; outputTokens: number | null;
  totalTokens: number | null; wastedTokens: number | null;
  conflicts: number; retries: number; nodesReexecuted: number; nodesPreserved: number;
}
export interface EventPayloads {
  demo_started: { scenario: ScenarioType; resourceKey: string; workerATask: string; workerBTask: string };
  resource_initialized: { resource: ResourceState; resourceKey: string };
  agent_read: { agentId: AgentId; nodeId: string; version: number; resource: ResourceState };
  agent_decision: { agentId: AgentId; summary: string };
  resource_write: { agentId: AgentId; nodeId: string; resource: ResourceState };
  conflict_detected: { agentId: AgentId; expectedVersion: number; actualVersion: number };
  semantic_audit_started: Record<string, never>;
  semantic_audit_completed: AuditResult;
  dependency_analysis_completed: RecoveryResult;
  recovery_started: RecoveryResult;
  recovery_step: { nodeId: string; summary: string };
  recovery_completed: RecoveryResult;
  final_state: { resource: ResourceState; verified: boolean };
  metrics: DemoMetrics;
  demo_completed: { verified: boolean };
  demo_failed: { message: string };
}
export type EventType = keyof EventPayloads;
export type DemoEvent = { [K in EventType]: {
  id: number; timestamp: string; type: K; data: EventPayloads[K];
} }[EventType];
export interface DemoState {
  status: DemoStatus; events: DemoEvent[]; resourceKey?: string;
  resource?: ResourceState; resourceHistory: ResourceState[];
  agents: Record<AgentId, AgentState>; audit?: AuditResult; auditing: boolean;
  recovery?: RecoveryResult; recovered: boolean; metrics?: DemoMetrics;
  final?: ResourceState; conflict?: EventPayloads["conflict_detected"]; error?: string;
}
