# Dependency-Aware MCP

A Python research prototype for shared, versioned MCP resources in concurrent
agent workflows.

> This system is a research prototype for dependency-aware optimistic concurrency control in concurrent LLM-agent workflows using MCP. LangGraph and Deep Agents provide orchestration and reasoning infrastructure; the research contribution is the MCP provenance, semantic conflict analysis, dependency-aware invalidation, and selective recovery mechanism.

## Current milestone

**Milestone 1 base, specification sections 55–56.**

Implemented: async SQLite storage, atomic optimistic version validation,
transactional read/write provenance, recorded read dependencies and structural
conflicts, MCP read/write/list tools, and FastAPI health. Deterministic async
workers reproduce the stale-write problem in storage and MCP HTTP tests.

Deep Agents and LangGraph execution are the next steps described after the base
in section 55. They are not installed or implemented in this step. Semantic
auditing, dependency graphs, selective recovery, locking protocols, experiments,
and benchmark statistics are deferred. The reserved modules contain only
docstrings; `benchmarks/scenarios.json` is an empty array.

## Architecture

```text
FastAPI control plane :8000             Trusted runtime / test workers A and B
  GET /health                                      |
  lifespan initializes DB              MCP Streamable HTTP :8001/mcp
                |                        read / write / list tools
                |                                  |
                |                      runtime identity -> ContextVar
                |                                  |
                |                       version service + provenance
                |                                  |
                +---------------------- shared SQLite file
```

FastAPI and MCP run as separate processes using the same database path.
FastAPI does not connect to MCP or launch a workflow in this base.

Each resource starts at version 1. Writes replace the entire JSON object and
increment the version through a single conditional SQL operation:

```sql
UPDATE resources
SET value_json = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
WHERE resource_key = ? AND version = ?;
```

An affected-row count of zero produces a typed `VersionConflict` for an existing
resource. A missing key produces `ResourceNotFound`. The actual version is read
in the same transaction. The conflict row commits before the exception leaves
the service. A failed write never creates a successful WRITE log.

Successful writes and their provenance share one transaction. Reads and lists
also record their exact returned snapshots as READ logs and dependencies in a
transaction. A list exposes values, so every listed resource is logged.
WRITE logs store the resulting version; the previous version is one less.

SQLite WAL mode, a busy timeout, and short `BEGIN IMMEDIATE` transactions coordinate
database operations across connections and processes. These transactions end
before any worker reasoning interval; there is no application-level 2PL.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

Run from this project directory:

```powershell
uv sync --locked
Copy-Item .env.example .env
uv run python -m app.storage.seed
```

If uv was installed through pip and is unavailable on PATH, replace `uv` with
`python -m uv` in these commands. The seed creates
`inventory/product_1@v1` with quantity 100, price 20, and description "Product A".
Running the seed again preserves existing values and versions.

Both servers initialize all five tables and create the database's parent
directory during startup. No database is created at import time.
`DATABASE_PATH` is relative to the process's working directory, so run both
servers from this directory or configure an absolute path.

No model provider or API key is needed for this milestone. The MODEL and
AUDITOR_MODEL settings are reserved for later work.

## Run FastAPI

In one terminal:

```powershell
uv run python -m app.main
```

In another:

```powershell
curl.exe http://127.0.0.1:8000/health
```

Expected: `{"status":"ok"}`.

API_HOST and API_PORT configure this entry point. Run, resource-management, and
metrics endpoints are reserved for later milestones.

## Run MCP

In a separate terminal, from the same directory:

```powershell
uv run python -m app.mcp_server.server
```

The default endpoint is `http://127.0.0.1:8001/mcp`, using Streamable HTTP with
stateless transport and JSON responses. MCP_HOST and MCP_PORT configure the
server. MCP_URL is reserved for client configuration.

Model-facing tools:

| Tool | Arguments | Result |
|---|---|---|
| read_shared_resource | resource_key | resource_key, value, version, updated_at |
| write_shared_resource | resource_key, new_value, expected_version | status=ok and updated resource, or structured conflict |
| list_shared_resources | none | resources array with values and versions |

A stale write returns structured content such as:

```json
{
  "status": "conflict",
  "resource_key": "inventory/product_1",
  "expected_version": 1,
  "current_version": 2
}
```

The tools return structured application errors for a missing resource or missing
runtime identity. Invalid arguments produce an MCP tool error. No tool restarts
a worker or workflow.

## Runtime provenance identity

The trusted client runtime supplies **X-Run-Id**, **X-Agent-Id**, and **X-Node-Id**
HTTP headers on each tool request. MCP's injected Context reads these headers
and binds a validated ExecutionIdentity to a ContextVar for the operation.
The binding resets on exit. Identity is never part of a model-facing tool
schema. Plain ContextVars cannot transfer identity to a separate server process.

These headers are a convention for this local research prototype, not an
authentication mechanism. Keep the service on loopback. A later worker adapter
must set headers programmatically and update node identity as graph nodes
change. Do not ask a model to supply them.

For an MCP SDK v2 client, configure headers on `httpx2.AsyncClient`, pass that
client to `streamable_http_client(..., http_client=http)`, and wrap the transport
in `async with Client(transport)`. The working HTTP integration tests demonstrate
this pattern.

## Tests and deterministic reproduction

```powershell
uv run pytest
```

To see the forced race and its log messages:

```powershell
uv run pytest tests/test_api.py::test_mcp_two_independent_runtime_clients_reproduce_race -v -o log_cli=true --log-cli-level=INFO
```

This test starts its own local MCP server on an available port and uses an
isolated temporary SQLite file. It requires no manually running services or LLM.
Two independent runtime clients use asyncio events to guarantee this order:

```text
A: READ X@v1 ------------------------------ WRITE expected v1 -> conflict
B:              READ X@v1 -> WRITE X@v2
```

Tests cover resource replacement, missing resources, idempotent initialization,
stale writes, eight competing writers with one winner, provenance and dependency
records, rollback when provenance fails, identity isolation and cleanup,
FastAPI lifespan and health, MCP tool schemas, argument errors, and calls over
real local Streamable HTTP.

## Files

```text
app/
  config.py                      pydantic-settings configuration
  main.py                        FastAPI factory, lifespan, health, CLI
  api/{runs,resources,metrics}.py reserved modules
  agents/{workers,auditor}.py     reserved modules
  graph/                         reserved state/workflow/nodes/recovery modules
  mcp_server/server.py           MCP v2 factory, lifespan, HTTP CLI
  mcp_server/tools.py            tools and runtime identity bridge
  concurrency/conflicts.py       typed domain exceptions
  concurrency/provenance.py      ContextVar identity and audit inserts
  concurrency/version_manager.py transactional resource service
  concurrency/dependency_graph.py reserved module
  concurrency/locks.py           reserved module
  storage/database.py            schema, connections, transactions, init_db
  storage/repositories.py        resource SQL and audit queries
  storage/seed.py                non-destructive example seed CLI
  schemas/{resource,conflict}.py  Pydantic resource and conflict contracts
  schemas/experiment.py          reserved module
benchmarks/{scenarios.json,runner.py} reserved benchmark files
tests/conftest.py                 temporary DB and real HTTP server fixtures
tests/test_resources.py           resource storage and versioning
tests/test_occ.py                 deterministic races and atomic writes
tests/test_provenance.py          audit consistency and identity isolation
tests/test_api.py                 health and MCP HTTP integration
data/.gitkeep
.env.example
.gitignore
.python-version
pyproject.toml
uv.lock
README.md
```

Each app package includes `__init__.py`. The lockfile records the complete
resolved dependency set. The local virtual environment and database files are
ignored by Git.

## API and version assumptions

- Python 3.11+; this implementation was tested on Python 3.11.9.
- MCP SDK **2.3.0** is locked; the supported dependency range is `>=2.3,<3`.
  The v2 API uses `from mcp.server import MCPServer`, the injected
  `mcp.server.mcpserver.Context`, and transport settings on `run()` or
  `streamable_http_app()`. There is no v1 FastMCP fallback.
- MCP v2 clients use `httpx2`, while FastAPI tests use `httpx`.
  SDK result attributes use `structured_content`, `input_schema`, and `is_error`.
- See the official [v2 release notes](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.3.0)
  and [migration guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md).
- Resource creation is administrative setup only. There is no public create or
  reset tool. SQL is parameterized, and models cannot provide SQL or provenance.
- All required tables exist now, but runs and semantic fields are not populated
  until their respective milestones.

## Next steps

The next smallest step is one mockable Deep Agent using a persistent MCP client
and runtime-supplied identity. Add two parallel LangGraph workers only after that
single-worker path works.

Subsequent milestones remain separate:

1. Complete the agent and parallel LangGraph portion of reproducing the problem.
2. Semantic classification with structured decisions and ground-truth labels.
3. Dependency graph and affected-node discovery.
4. Selective recovery that preserves valid sibling work.
5. The naive, 2pl, occ, and dependency_occ experimental protocols.
6. Repeated benchmarking and comparative metrics.

