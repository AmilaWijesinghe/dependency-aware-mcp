import type { DemoEvent } from "@/lib/types";
import { describeEvent } from "@/lib/demo-events";

export function TimelineEvent({ event, start }: { event: DemoEvent; start: number }) {
  const tone = event.type.includes("conflict") || event.type === "demo_failed" ? "red" : event.type.includes("audit") ? "purple" : event.type.includes("recovery") ? "orange" : event.type.includes("write") || event.type.includes("final") || event.type === "demo_completed" ? "green" : "blue";
  const label = event.type === "conflict_detected" ? "CONFLICT" : event.type.includes("audit") ? "AUDIT" : event.type.includes("recovery") ? "RECOVERY" : event.type === "agent_read" ? "READ" : event.type === "resource_write" ? "WRITE" : event.type === "final_state" ? "VERIFIED" : "SYSTEM";
  const elapsed = Math.max(0, (Date.parse(event.timestamp) - start) / 1000);
  return <li className={`timeline-row timeline-${tone}`}>
    <span className="timeline-marker" /><div className="min-w-0"><div className="flex items-center justify-between gap-3"><span className="timeline-label">{label}</span><time dateTime={event.timestamp}>+{elapsed.toFixed(2)}s</time></div><p>{describeEvent(event)}</p></div>
  </li>;
}
