import { ArrowRight, Boxes, CircleDollarSign, Play, RotateCcw } from "lucide-react";
import type { DemoStatus, Scenario, ScenarioType } from "@/lib/types";

export function ScenarioSelector({ scenarios, selected, status, onSelect, onRun, onReset }: {
  scenarios: Scenario[]; selected: ScenarioType; status: DemoStatus;
  onSelect: (id: ScenarioType) => void; onRun: () => void; onReset: () => void;
}) {
  const running = status === "running";
  return <section className="scenario-panel">
    <p className="eyebrow">01 / Configure</p><h2>Choose a scenario</h2>
    <p className="muted text-sm mt-2 mb-6">Two workers. One shared resource.<br />A different kind of conflict.</p>
    <div className="space-y-3" role="group" aria-label="Demo scenario">
      {scenarios.map((scenario, index) => {
        const Icon = scenario.id === "non_disruptive" ? CircleDollarSign : Boxes;
        return <button key={scenario.id} type="button" aria-pressed={selected === scenario.id}
          disabled={running} onClick={() => onSelect(scenario.id)}
          className={`scenario-option ${selected === scenario.id ? "selected" : ""}`}>
          <span className="flex justify-between items-center mb-5"><Icon size={22} strokeWidth={1.6} /><span className="scenario-radio" /></span>
          <span className="eyebrow">Scenario 0{index + 1}</span>
          <strong className="block mt-1 mb-2">{scenario.name}</strong>
          <span className="block text-xs leading-relaxed muted">{scenario.description}</span>
          <span className="scenario-outcome">{scenario.id === "non_disruptive" ? "Independent decisions" : "State-dependent decision"}<ArrowRight size={13} /></span>
        </button>;
      })}
    </div>
    <button type="button" className="run-button" disabled={running || !scenarios.length} onClick={onRun}>
      <Play size={15} fill="currentColor" />{running ? "Execution in progress" : "Run demonstration"}
    </button>
    {(status === "completed" || status === "failed") && <button className="reset-button" onClick={onReset}><RotateCcw size={14} />Reset workspace</button>}
    <div className="scenario-note"><span className="small-square" /><p>Live backend execution<br /><span className="muted">Each run uses an isolated resource.</span></p></div>
  </section>;
}
