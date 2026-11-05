import { Activity, ArrowDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { DemoEvent } from "@/lib/types";
import { Panel } from "./Panel";
import { TimelineEvent } from "./TimelineEvent";

export function Timeline({ events }: { events: DemoEvent[] }) {
  const list = useRef<HTMLOListElement>(null);
  const [follow, setFollow] = useState(true);
  useEffect(() => { if (follow && list.current) list.current.scrollTop = list.current.scrollHeight; }, [events, follow]);
  return <Panel title="Execution timeline" eyebrow="02 / Observe" className="timeline-panel" action={<span className="text-xs muted font-mono">{String(events.length).padStart(2, "0")} EVENTS</span>}>
    <div className="timeline-toolbar"><span><Activity size={13} />Backend event stream</span><button type="button" aria-pressed={follow} onClick={() => setFollow(!follow)}><ArrowDown size={12} />Auto-follow {follow ? "on" : "off"}</button></div>
    {events.length ? <ol className="timeline-list" ref={list} aria-label="Execution events">{events.map(event => <TimelineEvent key={event.id} event={event} start={Date.parse(events[0].timestamp)} />)}</ol> : <div className="timeline-empty"><span className="empty-icon"><Activity size={28} strokeWidth={1.3} /></span><h3>Every step, as it happens.</h3><p>Start a demonstration to follow reads, commits,<br />conflict detection and recovery here.</p><div className="empty-flow">READ <span>→</span> CONFLICT <span>→</span> RECOVER</div></div>}
  </Panel>;
}
