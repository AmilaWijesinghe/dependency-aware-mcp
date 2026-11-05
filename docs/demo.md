# Local frontend demonstration

This dashboard observes the existing Phase 4 LangGraph workflow. It is separate
from formal evaluation. Worker and Auditor prompts, held-out scenarios, and evaluation evidence are
kept separate from the presentation.

## Prerequisites

- Python 3.11+ and the existing project environment (`uv sync --locked`).
- Node.js 24 LTS (tested), npm, and Chrome for optional browser tests.
- Reachable MongoDB, Ollama with the configured models installed, and MCP.
- Run every Python command from `backend/`, so the existing `.env`
  is loaded by the research configuration.

The backend `.env` must define `MONGODB_URI` and `OLLAMA_MODEL`.
Supported optional settings are `MONGODB_DATABASE`, `OLLAMA_BASE_URL`,
`OLLAMA_AUDITOR_MODEL`, and `MCP_URL`. Keep your existing values. For example,
a local installation can use:

```dotenv
MONGODB_URI=mongodb://127.0.0.1:27017
MONGODB_DATABASE=dependency_aware_mcp
OLLAMA_MODEL=your-installed-model
OLLAMA_BASE_URL=http://127.0.0.1:11434
MCP_URL=http://127.0.0.1:8001/mcp
```

The frontend contains no backend credentials. Its only configuration is
`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` in `frontend/.env.local`.

## Run the real demonstration

Start your configured MongoDB service. Start Ollama if it is not already running:

```powershell
ollama serve
```

Terminal 1 — existing MCP server:

```powershell
Set-Location backend  # from the repository root
uv sync --locked
uv run python -m app.mcp_server.server
```

Terminal 2 — demo API:

```powershell
Set-Location backend  # from the repository root
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 3 — frontend:

```powershell
Set-Location frontend  # from the repository root
Copy-Item .env.example .env.local
npm.cmd ci
npm.cmd run dev
```

Open **http://localhost:3000**. Choose a scenario, run it, inspect the timeline,
then reset or choose the other scenario. `npm.cmd` avoids PowerShell's execution
policy restriction on `npm.ps1`.

For a production frontend preview, use `npm.cmd run build` followed by
`npm.cmd run start`. The API and MCP commands stay the same.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | API process liveness; does not assert external service readiness. |
| GET | `/api/demo/scenarios` | The two controlled scenario definitions and worker tasks. |
| POST | `/api/demo/run` | Start the real workflow with `{"scenario":"non_disruptive"}` or `{"scenario":"disruptive"}`. |
| GET | `/api/demo/events/{demo_id}` | SSE execution facts, including any backlog and terminal event. |

A successful start returns HTTP 202 and `demoId`, `resourceKey`, `eventsUrl`.
The key is always `demo/<UUID>/product_1`. Each start inserts a fresh resource;
it never resets another run's resource. Administrative initialization is the
only direct resource mutation outside MCP. Subsequent reads, commits and final
verification run through the existing MCP tools and concurrency middleware.

SSE frames contain an `id:` and `data:` JSON with `id`, `type`, `timestamp`, and
`data`. Reconnect with `Last-Event-ID` to receive only newer events. Heartbeat
comments keep idle streams alive. All subscribers receive the same journal;
disconnecting a browser does not cancel execution. The frontend deduplicates
event IDs and closes the stream on completion, failure or component unmount.

Supported events: `demo_started`, `resource_initialized`, `agent_read`,
`agent_decision`, `resource_write`, `conflict_detected`,
`semantic_audit_started`, `semantic_audit_completed`,
`dependency_analysis_completed`, `recovery_started`, `recovery_step`,
`recovery_completed`, `final_state`, `metrics`, `demo_completed`, `demo_failed`.

The local API uses one process, up to two concurrent runs, and at most 32 retained
run journals. Completed journals expire after one hour, pruned on the next API
lookup/start; capacity evicts the oldest completed journal. API restart/reload
loses the journals. Runs have a 15-minute deadline. MongoDB resources and
provenance remain available for inspection; the demo does not delete persisted
research data. CORS permits only localhost/127.0.0.1 on frontend port 3000.

## Interpreting the display

The unchanged graph supplies controlled initial write proposals to the existing
LLM workers. Both initial reads happen before B commits. The existing middleware
detects A's actual stale write. The existing Semantic Auditor classifies the
conflict and the existing dependency and recovery services select the path.
The UI does not impose a classification or simulate the race.

- Price vs. quantity: expected final quantity **60**, price **25**, version **3**;
  non-disruptive audit and rebase, with zero decision nodes re-executed.
- Inventory allocation: expected final quantity **30**, price **20**, version
  **3**; disruptive audit and selective recovery from quantity 60.

`affectedNodes` lists invalidated original graph nodes. The Phase 4 graph models
A with `a_read` and `a_stale_write`, and B with `b_read` and `b_write`; it has no
separate original `a_reason` node. `candidateNodes` retains the structural scan.
After a non-disruptive audit, semantic invalidation is empty and all four original
worker nodes are preserved. After a disruptive audit, the two original A nodes
are affected and B's two nodes are preserved. The three actually executed
recovery nodes are `recover_a_read`, `recover_a_reason`, `recover_a_commit`.
The UI shows these real node identifiers without inventing graph nodes.

Latency uses a monotonic clock. Conflict and commit-retry counts come from
persisted provenance. Token totals use provider usage callbacks; absent usage
appears as `—`. Wasted-token attribution is unavailable in this unchanged nested
graph and is always `—`, never a fabricated zero. Metrics describe only the demo
run and are not formal research results.

The stream allowlists execution facts and short structured summaries. It never
serializes worker messages, prompts, raw model responses or graph state. Server
exceptions are logged; the browser receives a safe error summary. A failed final
state check produces failure instead of a verified result.

## Validate

With the real services and API running:

```powershell
Set-Location backend  # from the repository root
uv run python scripts/validate_demo.py
```

This checks both real scenario runs, SSE, isolation, audit/recovery, version 3,
and exact final values. It exits nonzero on failure.

Independent integration tests (no MongoDB or Ollama required; run from `backend/`):

```powershell
uv run python -m unittest discover -s tests -p test_demo.py -v
uv run python -m unittest discover -s tests -p test_research_trace.py -v
```

The demo integration tests use the actual Phase 4 graph, MCP HTTP transport,
OCC middleware, repositories, audit service, dependency scan, rebase and recovery.
Only persistence and model inference are substituted in `tests/demo_support.py`.

Frontend validation:

```powershell
Set-Location frontend  # from the repository root
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
npm.cmd run test:browser
```

Browser tests start their own test-only API on port 8002 and frontend on 3000,
using installed Chrome. Keep those ports free. They exercise real SSE over local
HTTP, desktop/mobile rendering, both scenarios, reset, retry and command failure.
Screenshots are saved in ignored `frontend/test-results/`.
`scripts/serve_demo_test_api.py` is exclusively a test fixture with substitutes;
**do not use it for the live presentation**. The normal API never imports it.

Run the full isolated backend suite with `uv run pytest` from `backend/`.
The obsolete SQLite implementation and its fixtures have been retired.
