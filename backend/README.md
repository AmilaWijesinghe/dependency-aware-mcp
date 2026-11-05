# Backend

Python research runtime for dependency-aware concurrency control over shared MCP
resources. It uses FastAPI, MCP, LangGraph, Deep Agents, MongoDB, and Ollama.

## Setup

Run from this directory with Python 3.11+ and uv:

```sh
uv sync --locked
cp .env.example .env
```

Configure `MONGODB_URI` and `OLLAMA_MODEL`. Optional settings are
`MONGODB_DATABASE`, `OLLAMA_BASE_URL`, `OLLAMA_AUDITOR_MODEL`, and `MCP_URL`.
The environment template contains local defaults and no credentials.

Start MongoDB and Ollama, then run these commands in separate terminals from
this directory:

```sh
uv run python -m app.mcp_server.server
```

```sh
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

MCP listens at `http://127.0.0.1:8001/mcp`; the API listens on port 8000.
`GET /health` reports API liveness, while `/docs` describes the API routes.
The demo creates a fresh namespaced resource for each run.

## Architecture

- `app/api/` and `app/demo/`: demo control endpoints, event journals, and execution.
- `app/mcp_server/` and `app/mcp_client/`: tools, transport, and runtime provenance.
- `app/concurrency/`: OCC middleware, semantic auditing, dependencies, and recovery.
- `app/agents/` and `app/graph/`: workers, auditor, and workflow orchestration.
- `app/storage/`: MongoDB collections, indexes, and repositories.
- `app/protocols/` and `app/evaluation/`: baseline protocols, scenarios, and metrics.
- `scripts/`: benchmark commands, diagnostics, and service-dependent checks.
- `tests/`: isolated tests using substitute storage and model inference.

## Tests

```sh
uv run pytest
uv run python -m unittest scripts.test_phase6_runner
uv run python -m scripts.validate_heldout_scenarios
```

These checks do not need running MongoDB or Ollama, but settings must be supplied
via `.env` or environment variables. CI uses a local MongoDB URI and `test-model`.
Additional `scripts/test_*.py` files include live service checks; consult their
docstrings before running them. See [development](../docs/development.md).

## Formal evaluation

With MongoDB, Ollama, and MCP running and the models configured:

```sh
uv run python -m scripts.run_phase6_benchmark --scenario-set validation --repetitions 1
uv run python -m scripts.run_phase6_benchmark --scenario-set heldout --repetitions 10
uv run python -m scripts.summarize_phase6
```

The summary command reads the latest completed benchmark in MongoDB and writes
CSV exports to the ignored `results/` directory. It does not overwrite the
retained snapshot in `../reports/benchmarks/`. Each benchmark execution gets an
isolated resource key. Formal evaluation uses model inference and may take time.

To validate the dashboard scenarios against the live API:

```sh
uv run python -m scripts.validate_demo
```

See [the demo guide](../docs/demo.md) for scenario expectations and event details.
