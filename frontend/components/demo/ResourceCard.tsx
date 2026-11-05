import { Database } from "lucide-react";
import type { ResourceState } from "@/lib/types";
import { Panel } from "./Panel";
import { StatusBadge } from "./StatusBadge";

export function ResourceCard({ resource, resourceKey, history }: {
  resource?: ResourceState; resourceKey?: string; history: ResourceState[];
}) {
  return <Panel title="Shared resource" action={<StatusBadge tone={resource ? "green" : "neutral"}><Database size={12} />{resource ? `VERSION ${resource.version}` : "AWAITING RUN"}</StatusBadge>}>
    <div className="resource-fields">
      <div><span className="field-label">Quantity</span><strong>{resource?.quantity ?? "—"}<small>units</small></strong></div>
      <div><span className="field-label">Price</span><strong>{resource ? `$${resource.price.toFixed(2)}` : "—"}</strong></div>
      <div><span className="field-label">Description</span><strong className="resource-description">{resource?.description ?? "—"}</strong></div>
    </div>
    <div className="resource-footer"><code title={resourceKey}>{resourceKey ?? "Resource key assigned on start"}</code>
      <div className="flex gap-2 items-center shrink-0" aria-label="Resource version history">{history.map((item, index) => <span key={item.version} className="flex gap-2 items-center"><span className={index === history.length - 1 ? "version active" : "version"}>v{item.version}</span>{index < history.length - 1 && <span className="muted">→</span>}</span>)}</div>
    </div>
  </Panel>;
}
