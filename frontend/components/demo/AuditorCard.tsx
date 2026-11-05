import { ScanLine } from "lucide-react";
import type { AuditResult, DemoState } from "@/lib/types";
import { Panel } from "./Panel";
import { StatusBadge } from "./StatusBadge";

export function AuditorCard({ audit, auditing, conflict }: { audit?: AuditResult; auditing: boolean; conflict?: DemoState["conflict"] }) {
  return <Panel title="Semantic Auditor" action={<ScanLine size={18} className="muted" />}>
    {conflict && <div className="conflict-notice"><strong>Version conflict detected</strong><span>Expected v{conflict.expectedVersion} · actual v{conflict.actualVersion}</span></div>}
    {audit ? <><div className="flex items-center justify-between gap-3 mb-3"><StatusBadge tone={audit.semanticResult === "disruptive" ? "red" : "green"}>{audit.semanticResult.replaceAll("_", " ")}</StatusBadge><span className="confidence">{Math.round(audit.confidence * 100)}% confidence</span></div><p className="audit-reason">{audit.reason || "No summary provided."}</p><div className="premise"><span className="field-label">Affected premises</span><p>{audit.affectedPremises.length ? audit.affectedPremises.join(" · ") : "None — the original decision remains valid."}</p></div></> : <p className="waiting-text">{auditing ? "Evaluating whether the concurrent change invalidates Worker A’s decision…" : "Classification appears after a real version conflict."}</p>}
  </Panel>;
}
