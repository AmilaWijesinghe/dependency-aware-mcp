"use client";

import { Activity, ArrowRight, FlaskConical, GitBranch, RefreshCw, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchDemoScenarios, startDemo, subscribeToDemoEvents } from "@/lib/api";
import { applyDemoEvent, initialState } from "@/lib/demo-events";
import type { DemoState, Scenario, ScenarioType } from "@/lib/types";
import { AgentCard } from "./AgentCard";
import { AuditorCard } from "./AuditorCard";
import { DependencyGraph } from "./DependencyGraph";
import { FinalStateCard } from "./FinalStateCard";
import { MetricsCard } from "./MetricsCard";
import { RecoveryCard } from "./RecoveryCard";
import { ResourceCard } from "./ResourceCard";
import { ScenarioSelector } from "./ScenarioSelector";
import { StatusBadge } from "./StatusBadge";
import { Timeline } from "./Timeline";

export function DemoDashboard() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selected, setSelected] = useState<ScenarioType>("non_disruptive");
  const [state, setState] = useState<DemoState>(() => initialState());
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string>();
  const [connection, setConnection] = useState("closed");
  const close = useRef<(() => void) | undefined>(undefined);
  const mounted = useRef(true);
  const starting = useRef(false);
  const generation = useRef(0);

  const load = useCallback(async () => {
    setLoading(true); setApiError(undefined);
    try {
      const items = await fetchDemoScenarios();
      if (!mounted.current) return;
      setScenarios(items); setState(initialState(items[0]));
    } catch (error) { if (mounted.current) setApiError((error as Error).message); }
    finally { if (mounted.current) setLoading(false); }
  }, []);

  useEffect(() => {
    mounted.current = true; void load();
    return () => { mounted.current = false; generation.current += 1; close.current?.(); };
  }, [load]);

  async function run() {
    if (starting.current || state.status === "running") return;
    starting.current = true;
    const current = ++generation.current;
    close.current?.();
    setConnection("connecting");
    setState({ ...initialState(scenarios.find(item => item.id === selected)), status: "running" });
    const fail = (message: string) => {
      if (!mounted.current || current !== generation.current) return;
      setConnection("closed");
      setState(previous => ({ ...previous, status: "failed", error: message, auditing: false,
        agents: Object.fromEntries(Object.entries(previous.agents).map(([id, agent]) => [id,
          { ...agent, status: agent.status === "completed" ? "completed" : "stopped" }])) as DemoState["agents"],
      }));
    };
    try {
      const result = await startDemo(selected);
      if (!mounted.current || current !== generation.current) return;
      setState(previous => ({ ...previous, resourceKey: result.resourceKey }));
      close.current = subscribeToDemoEvents(result.demoId, event => {
        if (mounted.current && current === generation.current) setState(previous => applyDemoEvent(previous, event));
      }, value => { if (mounted.current && current === generation.current) setConnection(value); }, fail);
    } catch (error) { fail((error as Error).message); }
    finally { starting.current = false; }
  }

  function select(id: ScenarioType) {
    close.current?.(); setSelected(id); setState(initialState(scenarios.find(item => item.id === id)));
  }
  function reset() { close.current?.(); generation.current += 1; setConnection("closed"); setState(initialState(scenarios.find(item => item.id === selected))); }
  const running = state.status === "running";

  return <div className="app-shell">
    <header className="topbar"><a href="/" className="brand"><span className="brand-icon"><GitBranch size={21} strokeWidth={1.6} /></span><span>dependency<span className="brand-light">lab</span><span className="brand-period">.</span></span></a><div className="topbar-divider" /><span className="topbar-label">Multi-Agent MCP Research</span><span className="header-pill"><FlaskConical size={13} />BSc research prototype</span></header>
    <main className="page-container">
      <div className="breadcrumb">RESEARCH WORKSPACE <ArrowRight size={12} /><span>LIVE DEMONSTRATION</span></div>
      <div className="page-intro"><div><p className="eyebrow accent-text">Concurrency, with context.</p><h1>Dependency-aware<br className="mobile-break" /> multi-agent MCP</h1><p className="subtitle">Semantic conflict validation and selective recovery for shared agent state.</p></div><div className="intro-meta"><StatusBadge tone={state.status === "completed" ? "green" : state.status === "failed" ? "red" : running ? "orange" : "neutral"} dot>{state.status === "idle" ? "Ready to explore" : state.status}</StatusBadge><span className="protocol-tag">Dependency-aware Semantic OCC</span></div></div>
      <div className="process-strip"><span className="process-label"><Activity size={14} />EXECUTION PATH</span>{["Read", "Concurrent update", "Conflict", "Semantic audit", "Recovery", "Final state"].map((step, index) => <span className="process-step" key={step}>{index > 0 && <ArrowRight size={12} />}<span>{step}</span></span>)}</div>
      {apiError && <div className="error-banner" role="alert"><TriangleAlert size={19} /><div><strong>Demo API is unavailable</strong><p>{apiError}</p></div><button onClick={() => void load()}><RefreshCw size={14} />Retry connection</button></div>}
      {state.error && <div className="error-banner" role="alert"><TriangleAlert size={19} /><div><strong>Demo failed</strong><p>{state.error}</p></div></div>}
      <div className="demo-layout">
        <aside><ScenarioSelector scenarios={scenarios} selected={selected} status={state.status} onSelect={select} onRun={() => void run()} onReset={reset} />{loading && <p className="loading-note" role="status">Connecting to the demo API…</p>}<div className="aside-caption"><span className="eyebrow">The research question</span><p>Does a version conflict<br />always invalidate the work?</p><span>Follow the evidence.</span></div></aside>
        <div className="workspace min-w-0"><div className="workspace-heading"><span className="eyebrow">Live workspace</span><span className="connection-state" role="status"><span className={`connection-dot ${connection === "connected" ? "connected" : ""}`} />{running ? connection === "connected" ? "Receiving live events" : connection === "reconnecting" ? "Reconnecting…" : "Connecting…" : state.status === "completed" ? "Stream complete" : "Waiting for execution"}</span></div>
          <ResourceCard resource={state.resource} resourceKey={state.resourceKey} history={state.resourceHistory} />
          <div className="workers-grid"><AgentCard agent={state.agents.worker_a} /><AgentCard agent={state.agents.worker_b} /></div>
          <div className="execution-grid"><Timeline events={state.events} /><div className="research-panels"><AuditorCard audit={state.audit} auditing={state.auditing} conflict={state.conflict} /><DependencyGraph recovery={state.recovery} /><RecoveryCard recovery={state.recovery} completed={state.recovered} /></div></div>
          <FinalStateCard resource={state.final} /><MetricsCard metrics={state.metrics} />
        </div>
      </div>
      <footer className="page-footer"><span><span className="footer-dot" />Controlled demonstration · Real backend execution</span><span>Dependency-Aware MCP / Research Prototype</span></footer>
    </main>
  </div>;
}
