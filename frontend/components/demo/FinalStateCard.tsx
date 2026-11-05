import { CircleCheck, Flag } from "lucide-react";
import type { ResourceState } from "@/lib/types";

export function FinalStateCard({ resource }: { resource?: ResourceState }) {
  return <section className={`final-state ${resource ? "final-verified" : ""}`}><div className="flex items-center gap-3">{resource ? <CircleCheck size={23} /> : <Flag size={21} />}<div><p className="eyebrow">03 / Verify</p><h2>{resource ? "Consistent state. Valid work preserved." : "Final state awaits verification"}</h2></div></div>{resource ? <div className="final-values"><span>quantity <b>{resource.quantity}</b></span><span>price <b>${resource.price}</b></span><span>{resource.description}</span><span className="version active">v{resource.version}</span></div> : <span className="text-xs muted">Verified through a final MCP read</span>}</section>;
}
