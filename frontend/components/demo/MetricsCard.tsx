import type { DemoMetrics } from "@/lib/types";
import { Panel } from "./Panel";

export function MetricsCard({ metrics }: { metrics?: DemoMetrics }) {
  const format = (value?: number | null) => value == null ? "—" : value.toLocaleString();
  const items = [
    ["Conflicts", format(metrics?.conflicts)], ["Commit retries", format(metrics?.retries)],
    ["Latency", metrics ? `${(metrics.elapsedMs / 1000).toFixed(2)}s` : "—"],
    ["Total tokens", format(metrics?.totalTokens)], ["Wasted tokens", format(metrics?.wastedTokens)],
    ["Nodes re-executed", format(metrics?.nodesReexecuted)], ["Nodes preserved", format(metrics?.nodesPreserved)],
  ];
  return <Panel title="Demo run metrics" eyebrow="04 / Measure" className="metrics-panel" action={<span className="text-xs muted">This execution only</span>}>
    <dl className="metrics-grid">{items.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>
    <p className="metrics-footnote">{metrics ? "Measured from this run. Token totals use provider usage; wasted-token attribution is unavailable (—)." : "Metrics arrive when execution completes. Values are measured by the backend."}</p>
  </Panel>;
}
