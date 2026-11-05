import type { DemoEvent, Scenario, ScenarioType } from "./types";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, cache: "no-store", signal: AbortSignal.timeout(15000) });
  } catch {
    throw new Error("Cannot reach the demo API. Start FastAPI on port 8000, then retry.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Demo API returned ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

export function fetchDemoScenarios(): Promise<Scenario[]> { return request("/api/demo/scenarios"); }
export function startDemo(scenario: ScenarioType): Promise<{ demoId: string; resourceKey: string }> {
  return request("/api/demo/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario }) });
}

export function subscribeToDemoEvents(demoId: string, onEvent: (event: DemoEvent) => void,
  onConnection: (state: "connected" | "reconnecting" | "closed") => void,
  onFatal: (message: string) => void): () => void {
  const source = new EventSource(`${API_URL}/api/demo/events/${encodeURIComponent(demoId)}`);
  let failures = 0;
  source.onopen = () => { failures = 0; onConnection("connected"); };
  source.onmessage = message => {
    let event: DemoEvent;
    try { event = JSON.parse(message.data) as DemoEvent; }
    catch { source.close(); onFatal("The event stream returned invalid data. Start a new run."); return; }
    onEvent(event);
    if (event.type === "demo_completed" || event.type === "demo_failed") {
      source.close(); onConnection("closed");
    }
  };
  source.onerror = () => {
    failures += 1;
    if (source.readyState === EventSource.CLOSED || failures >= 5) {
      source.close(); onConnection("closed");
      onFatal("The event stream disconnected. The API may have restarted or the run expired. Start a new run.");
    } else onConnection("reconnecting");
  };
  return () => source.close();
}
