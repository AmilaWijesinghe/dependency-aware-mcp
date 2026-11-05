import { ArrowRight, GitBranch } from "lucide-react";
import type { RecoveryResult } from "@/lib/types";
import { Panel } from "./Panel";
import { StatusBadge } from "./StatusBadge";

const labels: Record<string, string> = { a_read: "A · read", a_stale_write: "A · stale commit", b_read: "B · read", b_write: "B · commit" };
const label = (id: string) => labels[id] ?? (id.startsWith("resource:") ? `Resource · ${id.split(":").at(-1)}` : id);

export function DependencyGraph({ recovery }: { recovery?: RecoveryResult }) {
  return <Panel title="Dependency map" action={<GitBranch size={18} className="muted" />}>
    {recovery ? <><div className="dependency-edges">{recovery.edges.map(edge => <div className="dependency-edge" key={`${edge.source}-${edge.target}`}><span className={`graph-node ${recovery.affectedNodes.includes(edge.source) ? "node-affected" : "node-preserved"}`}>{label(edge.source)}</span><ArrowRight size={14} /><span className={`graph-node ${recovery.affectedNodes.includes(edge.target) ? "node-affected" : "node-preserved"}`}>{label(edge.target)}</span></div>)}</div><div className="flex flex-wrap gap-2 mt-4"><StatusBadge tone="orange">{recovery.affectedNodes.length} affected</StatusBadge><StatusBadge tone="green">{recovery.nodesPreserved} preserved</StatusBadge></div><p className="text-xs muted mt-3 leading-relaxed">{recovery.strategy === "rebase" ? "No reasoning nodes invalidated. Reuse the valid A decision and preserve B’s commit." : "Only A’s dependent branch is invalidated. B’s completed work is preserved."}</p></> : <div className="dependency-placeholder"><GitBranch size={25} strokeWidth={1.2} /><p>Read dependencies and affected nodes<br />appear after semantic validation.</p></div>}
  </Panel>;
}
