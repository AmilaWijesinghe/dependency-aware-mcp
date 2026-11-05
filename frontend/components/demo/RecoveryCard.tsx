import { Check, RotateCcw } from "lucide-react";
import type { RecoveryResult } from "@/lib/types";
import { Panel } from "./Panel";
import { StatusBadge } from "./StatusBadge";

export function RecoveryCard({ recovery, completed }: { recovery?: RecoveryResult; completed: boolean }) {
  return <Panel title="Recovery strategy" action={<RotateCcw size={17} className="muted" />}>
    {recovery ? <><div className="flex items-center justify-between gap-2 mb-3"><StatusBadge tone={recovery.strategy === "rebase" ? "green" : "orange"}>{recovery.strategy === "rebase" ? "Rebase" : "Selective re-execution"}</StatusBadge>{completed && <Check size={16} className="text-emerald-700" />}</div><p className="audit-reason">{recovery.strategy === "rebase" ? "Apply A’s intended fields to the current state. Reuse the original decision." : "Read the fresh quantity, recalculate the allocation, then commit only A’s branch."}</p><div className="recovery-counts"><span><b>{completed ? recovery.nodesReexecuted : "…"}</b>nodes re-executed</span><span><b>{recovery.nodesPreserved}</b>nodes preserved</span></div>{recovery.reexecutedNodes.length > 0 && <div className="node-list">{recovery.reexecutedNodes.map(node => <code key={node}>{node}</code>)}</div>}</> : <p className="waiting-text">The audit determines whether to rebase or selectively re-execute.</p>}
  </Panel>;
}
