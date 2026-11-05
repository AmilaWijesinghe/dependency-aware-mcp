# Dependency-Aware MCP

A research prototype for coordinating concurrent LLM agents that share mutable
resources through the Model Context Protocol (MCP). It combines optimistic
concurrency control, provenance tracking, semantic conflict auditing, and
selective recovery of affected work.

The Next.js dashboard shows two controlled conflict scenarios using the Python
backend's LangGraph workflows. The evaluation code compares naive writes,
two-phase locking (2PL), full-restart OCC, and dependency-aware OCC.

## Repository layout

```text
backend/                 Python API, MCP server, agents, and evaluation
  app/                   Application code
  scripts/               Benchmarks, diagnostics, and live validation
  tests/                 Isolated automated tests
  .env.example           Backend configuration template
  pyproject.toml          Python dependencies
  uv.lock                Locked Python dependencies
frontend/                Next.js dashboard, components, and frontend tests
  .env.example           Public API URL template
  package-lock.json      Locked frontend dependencies
docs/                    Demo, development, and publishing guides
reports/                 Research report sources and build script
  benchmarks/            Retained benchmark evidence used by the report
.github/workflows/       Automated backend and frontend checks
```

## Requirements

- Python 3.11+ and uv.
- Node.js 24 and npm.
- MongoDB and Ollama for live workflows, with a tool-capable model installed.

The isolated automated tests substitute storage and model inference; they do not
require running MongoDB or Ollama.

## Local setup

From the repository root, install and configure the backend:

```sh
cd backend
uv sync --locked
cp .env.example .env
```

Set `OLLAMA_MODEL` in `backend/.env` to an installed model name. Set
`MONGODB_URI` to your database connection string. `OLLAMA_AUDITOR_MODEL` optionally
selects a separate auditor model. On PowerShell, use `Copy-Item` instead of `cp`
if preferred; use `npm.cmd` if execution policy blocks `npm.ps1`.

Install and configure the frontend, starting from the repository root:

```sh
cd frontend
npm ci
cp .env.example .env.local
```

With MongoDB and Ollama running, start these processes in separate terminals:

| Working directory | Command | Service |
| --- | --- | --- |
| `backend/` | `uv run python -m app.mcp_server.server` | MCP at `http://127.0.0.1:8001/mcp` |
| `backend/` | `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` | API at `http://127.0.0.1:8000` |
| `frontend/` | `npm run dev` | Dashboard at `http://127.0.0.1:3000` |

The demo initializes a separate resource for every run. API health is available
at `/health`; interactive API documentation is at `/docs`.

## Checks

Run backend checks from `backend/`:

```sh
uv run pytest
uv run python -m unittest scripts.test_phase6_runner
uv run python -m scripts.validate_heldout_scenarios
```

Run frontend checks from `frontend/`:

```sh
npm run typecheck
npm test
npm run build
```

Optional browser tests use installed Chrome and start their own isolated API and
frontend: `npm run test:browser`. See [development](docs/development.md) for details.

## Research and documentation

- [Demo guide](docs/demo.md): scenarios, API events, and live validation.
- [Backend guide](backend/README.md): architecture and benchmark commands.
- [Frontend guide](frontend/README.md): configuration and tests.
- [Reports](reports/README.md): evidence snapshots and regenerating report files.
- [Publishing guide](docs/publishing.md): checking what will be uploaded.

This is a local research system. Services bind to loopback; provenance headers
identify workflow execution and do not provide authentication. The dashboard
demonstration and formal evaluation are separate. The report describes the
retained benchmark snapshot, including its observed failures and limitations.
