import { Check, Cpu } from "lucide-react";
import type { AgentState } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";

export function AgentCard({ agent }: { agent: AgentState }) {
  const a = agent.agentId === "worker_a";
  const tone = agent.status === "conflict" ? "red" : agent.status === "completed" ? "green" : agent.status === "idle" || agent.status === "stopped" ? "neutral" : "blue";
  return <section className={`panel agent-panel ${a ? "agent-a" : "agent-b"}`}>
    <div className="flex items-center justify-between gap-2"><div className="flex items-center gap-3"><span className={`agent-avatar ${a ? "" : "avatar-b"}`}><Cpu size={18} /></span><div><h2>Worker {a ? "A" : "B"}</h2><p className="text-xs muted">{a ? "Primary operation" : "Concurrent operation"}</p></div></div><StatusBadge tone={tone} dot>{agent.status}</StatusBadge></div>
    <p className="agent-task">{agent.task}</p>
    <div className="agent-decision"><span className="field-label">Decision result</span><p>{agent.decision ?? "Waiting for execution…"}</p></div>
    <div className="agent-footer"><span>Read <b>{agent.readVersion ? `v${agent.readVersion}` : "—"}</b></span><span className="flex gap-1 items-center">{agent.writeVersion && <Check size={13} />}Commit <b>{agent.writeVersion ? `v${agent.writeVersion}` : "—"}</b></span></div>
  </section>;
}
