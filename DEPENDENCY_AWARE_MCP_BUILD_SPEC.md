# Dependency-Aware OCC for Multi-Agent MCP Systems
## Codex Build Specification

> **Purpose:** Use this file as the primary implementation brief for Codex in VS Code.
>
> Build the project incrementally. Do not skip milestones. Do not over-engineer the first version.
>
> The research goal is to evaluate whether **MCP read/write provenance + resource versioning + semantic conflict classification + dependency-aware selective re-execution** can reduce wasted tokens and latency compared with traditional full-restart OCC while maintaining correctness.

---

# 1. Core Research Question

Build a multi-agent system in which multiple LLM workers can concurrently interact with the same stateful MCP server.

The system must detect when:

1. Agent A reads a shared resource at version `v1`.
2. Agent B changes the same resource to version `v2`.
3. Agent A continues reasoning using the stale `v1` state.
4. A structural version conflict is detected.
5. A semantic auditor decides whether the state change actually invalidates Agent A's reasoning.
6. If the conflict is disruptive, only the affected execution subgraph is re-executed.
7. Unaffected sibling-agent work must be preserved.

The final system must support four experimental protocols:

- `naive`
- `2pl`
- `occ`
- `dependency_occ`

---

# 2. Technology Stack

Use:

- Python 3.11+
- FastAPI
- Uvicorn
- LangGraph
- LangChain
- Deep Agents (`deepagents`)
- MCP Python SDK v2
- LangChain MCP integration
- SQLite initially
- `aiosqlite`
- `networkx`
- `pydantic`
- `pydantic-settings`
- `python-dotenv`
- `httpx`
- `pytest`
- `pytest-asyncio`

Use `uv` for dependency management.

Do not add PostgreSQL, Redis, Docker, Celery, Kafka, or other infrastructure in the first milestone unless explicitly requested later.

---

# 3. High-Level Architecture

```text
                         CLIENT
                           |
                           v
                 +-------------------+
                 |      FastAPI      |
                 |                   |
                 | POST /runs        |
                 | GET  /runs/:id    |
                 | GET  /metrics     |
                 +---------+---------+
                           |
                           v
              +-------------------------+
              |        LangGraph        |
              |                         |
              |       START             |
              |      /     \            |
              |     /       \           |
              | Agent A    Agent B      |
              |    |          |         |
              |    +-----+----+         |
              |          v              |
              | Conflict Detector       |
              |          |              |
              | Semantic Auditor        |
              |          |              |
              | Recovery Router         |
              |      /       \          |
              | rerun A    preserve B   |
              |          |              |
              |        FINAL            |
              +----------+--------------+
                         |
                      MCP tools
                         |
                         v
           +----------------------------+
           | YOUR MCP CONCURRENCY LAYER |
           |                            |
           | Access Logger              |
           | Resource Version Manager   |
           | Dependency Recorder        |
           | OCC Validator              |
           +-------------+--------------+
                         |
                         v
                  Shared SQLite DB
```

Responsibilities must remain separated:

```text
Deep Agents
= reasoning workers

LangGraph
= execution topology, state, checkpointing, replay

FastAPI
= external API/control plane

MCP
= shared tool/resource interface

Concurrency middleware
= versioning, provenance, conflict detection

Semantic Auditor
= semantic conflict classification

Recovery Router
= selective invalidation and re-execution
```

---

# 4. Important Architectural Rule

Do **not** make the whole workflow one opaque Deep Agent.

Important execution stages must be explicit LangGraph nodes so selective subgraph recovery can be measured.

Bad:

```text
START
  |
DeepAgent
  |
 END
```

Preferred:

```text
START
  |
setup
 /   \
A_prepare   B_prepare
   |          |
A_reason    B_reason
   |          |
A_commit    B_commit
   \          /
    detect_conflicts
          |
    semantic_audit
          |
    recovery_router
          |
        finalize
```

Deep Agents may be called **inside** reasoning nodes.

---

# 5. Initial Project Structure

Create exactly this base layout:

```text
dependency-aware-mcp/
|
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── runs.py
│   │   ├── resources.py
│   │   └── metrics.py
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── workers.py
│   │   └── auditor.py
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py
│   │   ├── workflow.py
│   │   ├── nodes.py
│   │   └── recovery.py
│   │
│   ├── mcp_server/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   └── tools.py
│   │
│   ├── concurrency/
│   │   ├── __init__.py
│   │   ├── version_manager.py
│   │   ├── provenance.py
│   │   ├── conflicts.py
│   │   ├── dependency_graph.py
│   │   └── locks.py
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── repositories.py
│   │
│   └── schemas/
│       ├── __init__.py
│       ├── experiment.py
│       ├── resource.py
│       └── conflict.py
│
├── benchmarks/
│   ├── scenarios.json
│   └── runner.py
│
├── tests/
│   ├── test_resources.py
│   ├── test_occ.py
│   ├── test_provenance.py
│   └── test_api.py
│
├── data/
│   └── .gitkeep
│
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

---

# 6. Project Setup Commands

Use:

```bash
mkdir dependency-aware-mcp
cd dependency-aware-mcp

uv init

uv add fastapi "uvicorn[standard]"
uv add deepagents langgraph
uv add "langchain[mcp]>=1.4"
uv add "mcp[cli]"
uv add aiosqlite networkx
uv add pydantic pydantic-settings python-dotenv
uv add httpx

uv add --dev pytest pytest-asyncio
```

Install one LangChain-compatible model provider separately.

Example only:

```bash
uv add langchain-openai
```

Do not hardcode one provider into the architecture.

---

# 7. Environment Configuration

Create `.env.example`:

```env
MODEL=provider:model-name
AUDITOR_MODEL=provider:model-name

DATABASE_PATH=data/research.db

API_HOST=127.0.0.1
API_PORT=8000

MCP_HOST=127.0.0.1
MCP_PORT=8001
MCP_URL=http://127.0.0.1:8001/mcp
```

`app/config.py` must use `pydantic-settings`.

No API keys may appear in source code.

---

# 8. Database Schema

Use SQLite first.

## 8.1 resources

Fields:

```text
resource_key TEXT PRIMARY KEY
value_json TEXT NOT NULL
version INTEGER NOT NULL DEFAULT 1
updated_at TEXT
```

Example:

```json
{
  "resource_key": "inventory/product_1",
  "value": {
    "quantity": 100,
    "price": 20,
    "description": "Product A"
  },
  "version": 1
}
```

---

## 8.2 access_logs

Fields:

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
run_id TEXT NOT NULL
agent_id TEXT NOT NULL
node_id TEXT NOT NULL
resource_key TEXT NOT NULL
operation TEXT NOT NULL
version INTEGER NOT NULL
timestamp TEXT
```

Allowed operations:

```text
READ
WRITE
```

---

## 8.3 dependencies

Fields:

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
run_id TEXT NOT NULL
agent_id TEXT NOT NULL
node_id TEXT NOT NULL
resource_key TEXT NOT NULL
read_version INTEGER NOT NULL
timestamp TEXT
```

---

## 8.4 conflicts

Fields:

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
run_id TEXT NOT NULL
agent_id TEXT NOT NULL
node_id TEXT
resource_key TEXT NOT NULL
expected_version INTEGER NOT NULL
actual_version INTEGER NOT NULL
semantic_result TEXT
confidence REAL
timestamp TEXT
```

---

## 8.5 runs

Fields:

```text
run_id TEXT PRIMARY KEY
scenario_id TEXT
protocol TEXT NOT NULL
started_at TEXT
completed_at TEXT
success INTEGER
latency_ms REAL
prompt_tokens INTEGER DEFAULT 0
completion_tokens INTEGER DEFAULT 0
auditor_tokens INTEGER DEFAULT 0
retry_count INTEGER DEFAULT 0
tool_call_count INTEGER DEFAULT 0
conflict_count INTEGER DEFAULT 0
semantic_conflict_count INTEGER DEFAULT 0
rerun_node_count INTEGER DEFAULT 0
preserved_node_count INTEGER DEFAULT 0
wasted_tokens INTEGER DEFAULT 0
recovery_latency_ms REAL DEFAULT 0
```

---

# 9. Database Initialization

Implement `app/storage/database.py`.

Requirements:

- Create `data/` automatically if missing.
- Create all tables idempotently.
- Use async SQLite through `aiosqlite`.
- Provide `init_db()`.
- No ORM initially.

Use repository/service functions in `repositories.py`.

Avoid SQL logic inside FastAPI route handlers.

---

# 10. Resource Versioning

Every shared resource must have an integer version.

Example:

```text
product_1
version = 4
quantity = 100
```

Agent A reads:

```text
product_1@v4
```

Agent B updates it:

```text
product_1@v5
```

If Agent A later writes using:

```text
expected_version = 4
```

the write must fail structurally because:

```text
4 != 5
```

---

# 11. OCC Write Must Be Atomic

Do not implement:

```python
current = await read()

if current.version == expected_version:
    await update()
```

That creates a race.

Use one conditional SQL statement:

```sql
UPDATE resources
SET value_json = ?,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE resource_key = ?
  AND version = ?;
```

Then check affected row count.

If row count is zero:

```python
raise VersionConflict(...)
```

The OCC comparison and mutation must be one atomic database operation.

---

# 12. Custom Exceptions

Create clear exceptions:

```python
class ResourceNotFound(Exception):
    pass


class VersionConflict(Exception):
    def __init__(
        self,
        resource_key: str,
        expected_version: int,
        actual_version: int | None = None,
    ):
        ...
```

Do not return exceptions as unstructured strings internally.

---

# 13. Provenance Logging

Implement:

```python
async def log_read(...)
async def log_write(...)
async def record_dependency(...)
async def record_conflict(...)
```

A successful read must produce:

```text
Access log:
Agent A READ Resource X @ v3

Dependency:
Agent A / node a_reason -> Resource X @ v3
```

A successful write must produce:

```text
Agent B WRITE Resource X
v3 -> v4
```

---

# 14. MCP Server

Use MCP Python SDK v2.

Create:

```python
from mcp.server import MCPServer

mcp = MCPServer(
    "Dependency Aware Shared State"
)
```

Run the MCP server separately from FastAPI initially.

Target:

```text
http://127.0.0.1:8001/mcp
```

Use Streamable HTTP transport.

---

# 15. MCP Tools

At minimum implement:

```text
read_shared_resource
write_shared_resource
list_shared_resources
```

Optional later:

```text
create_resource
reset_resource
get_resource_history
```

---

# 16. MCP Read Tool Contract

The model-facing tool should conceptually be:

```python
read_shared_resource(resource_key: str)
```

The model must **not** provide:

```text
run_id
agent_id
node_id
```

Those must be injected by the runtime.

Internal operation:

```text
1. Get current resource value/version
2. Log READ
3. Record dependency
4. Return value + version
```

Example returned object:

```json
{
  "resource_key": "inventory/product_1",
  "value": {
    "quantity": 100,
    "price": 20
  },
  "version": 3
}
```

---

# 17. MCP Write Tool Contract

Model-facing conceptual tool:

```python
write_shared_resource(
    resource_key: str,
    new_value: dict,
    expected_version: int,
)
```

Runtime injects:

```text
run_id
agent_id
node_id
```

Expected behavior:

```text
1. Attempt atomic versioned write
2. If successful:
      increment version
      log WRITE
      return success
3. If version mismatch:
      record structural conflict
      return structured conflict result
4. Do not automatically restart the workflow here
```

Conflict response example:

```json
{
  "status": "conflict",
  "resource_key": "inventory/product_1",
  "expected_version": 3,
  "current_version": 4
}
```

---

# 18. Runtime Identity Injection

The LLM must never decide its own provenance identity.

Use `ContextVar` or equivalent request/graph context.

Example concept:

```python
from contextvars import ContextVar

current_run_id = ContextVar("current_run_id")
current_agent_id = ContextVar("current_agent_id")
current_node_id = ContextVar("current_node_id")
```

Inside each LangGraph node:

```python
run_token = current_run_id.set(state["run_id"])
agent_token = current_agent_id.set("worker_a")
node_token = current_node_id.set("a_reason")

try:
    ...
finally:
    current_run_id.reset(run_token)
    current_agent_id.reset(agent_token)
    current_node_id.reset(node_token)
```

MCP wrappers retrieve these values programmatically.

---

# 19. Test MCP Independently

Before connecting any LLM:

1. Start MCP server.
2. Test tools manually.
3. Verify resource versions.
4. Verify conflict behavior.
5. Verify provenance rows.

Use MCP Inspector if available.

Do not proceed to agents until this works.

---

# 20. FastAPI Application

Implement:

```text
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

Use FastAPI lifespan for:

- database initialization
- application resource initialization
- later MCP adapter setup
- later LangGraph setup

Do not place initialization logic at import-time when it can be done safely in lifespan.

---

# 21. LangChain MCP Connection

Connect LangChain/Deep Agents to the MCP server using the current LangChain MCP integration.

Keep the MCP adapter open for the FastAPI application lifetime.

Do not reconnect for every individual tool call.

Store initialized tools on:

```python
app.state.mcp_tools
```

or in a dedicated dependency/service object.

---

# 22. Deep Agent Workers

Create two independent workers:

```text
Worker A
Worker B
```

Do not invoke the same stateful agent instance concurrently.

Conceptual construction:

```python
from deepagents import create_deep_agent

worker_a = create_deep_agent(
    model=model,
    tools=worker_a_tools,
    system_prompt=...
)

worker_b = create_deep_agent(
    model=model,
    tools=worker_b_tools,
    system_prompt=...
)
```

System instructions must include:

```text
- Use shared MCP resources when required.
- Remember resource versions returned from reads.
- For writes, use the version obtained from the relevant read as expected_version.
- Never invent a version.
- Do not bypass shared-state tools.
```

---

# 23. Do Not Use Remote Async Subagents Initially

For the first research prototype, do not use Deep Agents remote async-subagent infrastructure.

Instead:

```text
LangGraph node A -> Worker A
LangGraph node B -> Worker B
```

Run those graph nodes concurrently.

This keeps the experimental system understandable and avoids adding infrastructure unrelated to the research question.

---

# 24. LangGraph State

Create `ResearchState`.

Minimum fields:

```python
class ResearchState(TypedDict, total=False):
    run_id: str
    scenario_id: str
    protocol: str

    task_a: str
    task_b: str

    prepared_a: dict
    prepared_b: dict

    output_a: str
    output_b: str

    conflicts: list[dict]
    semantic_decisions: list[dict]

    affected_nodes: list[str]

    retry_count: int

    final_output: dict
```

Add reducers only where parallel branch updates require them.

---

# 25. First LangGraph

First build only:

```text
        START
       /     \
worker_a     worker_b
       \     /
         join
          |
         END
```

Acceptance criterion:

- A and B genuinely overlap in time.
- Both can call the same MCP server.
- Both maintain independent LLM contexts.
- State merges cleanly at `join`.

---

# 26. Forced Race Conditions

Do not depend on random API timing.

Benchmark scenarios must support deterministic artificial delays.

Example:

```json
{
  "scenario_id": "inventory_001",
  "agent_a_delay_after_read_ms": 2000,
  "agent_b_delay_before_write_ms": 500
}
```

Target interleaving:

```text
Time ------------------------------------>

Agent A:
READ X@v1 -------- reasoning -------- WRITE expected v1
                 ^
Agent B:
          READ X@v1 -> WRITE X@v2

                                       ^
                                  conflict
```

Implement delay hooks in the controlled test environment, not by asking the LLM to "wait".

---

# 27. Structural Conflict Detector

After parallel work, compare recorded dependencies with current versions.

Algorithm:

```text
for each dependency:
    read_version = dependency.read_version
    current_version = resource.version

    if current_version > read_version:
        candidate structural conflict
```

Important:

```text
version mismatch != semantic invalidation
```

This stage only identifies potential stale dependencies.

---

# 28. Semantic Auditor

Build the auditor as a dedicated component.

Do not ask Worker A to judge whether Worker A is wrong.

Use a separate LLM call/node.

Structured schema:

```python
class SemanticConflictDecision(BaseModel):
    disruptive: bool
    affected_premises: list[str]
    reason: str
    confidence: float
```

The auditor receives:

```text
- task
- old resource value
- old version
- new resource value
- new version
- worker output/decision
- changed fields
- relevant node identity
```

Example:

```text
Task:
Allocate 50 units.

Old:
quantity = 100

New:
quantity = 40

Worker decision:
Allocate 50.
```

Expected:

```json
{
  "disruptive": true,
  "affected_premises": [
    "available inventory quantity"
  ],
  "reason": "The allocation relied on the previous quantity.",
  "confidence": 0.97
}
```

---

# 29. Semantic Non-Disruptive Example

Example:

Old:

```json
{
  "quantity": 100,
  "description": "Soap"
}
```

New:

```json
{
  "quantity": 100,
  "description": "Premium Soap"
}
```

Worker reasoning:

```text
Allocate 50 units.
```

The expected semantic result is:

```json
{
  "disruptive": false
}
```

This distinction is essential to the research contribution.

---

# 30. Ground Truth Labels

Every benchmark case involving a version conflict must contain a manually defined ground-truth semantic label.

Allowed:

```text
disruptive
non_disruptive
```

Do not evaluate the semantic auditor against its own output.

Calculate later:

- Accuracy
- Precision
- Recall
- F1

---

# 31. Dependency Graph

Use `networkx.DiGraph` initially.

Node examples:

```text
resource:inventory/product_1:v1
a_prepare
a_reason
a_commit
b_prepare
b_reason
b_commit
finalize
```

Example dependency:

```text
resource:X:v1
      |
      v
   a_reason
      |
      v
   a_commit
      |
      v
   finalize
```

If X becomes `v2` and semantic auditing says disruptive:

```python
affected = {
    start_node,
    *nx.descendants(G, start_node),
}
```

Persist or export graph structure for debugging.

---

# 32. Final Target LangGraph

Build toward:

```text
                     START
                       |
                 setup_scenario
                       |
           +-----------+-----------+
           |                       |
           v                       v
       A_prepare                B_prepare
           |                       |
           v                       v
       A_reason                 B_reason
           |                       |
           v                       v
       A_commit                 B_commit
           |                       |
           +-----------+-----------+
                       |
                       v
              detect_conflicts
                       |
                 conflict?
                 /       \
               no         yes
               |           |
               v           v
            finalize   semantic_audit
                            |
                      disruptive?
                       /       \
                     no         yes
                     |           |
                     v           v
                  finalize   dependency_scan
                                  |
                                  v
                            recovery_router
                               /      \
                              v        v
                         recover_a  recover_b
                              \        /
                               \      /
                            validate_again
                                  |
                                  v
                               finalize
```

---

# 33. LangGraph Checkpointing

Use a checkpointer.

Development default:

```python
from langgraph.checkpoint.memory import InMemorySaver
```

Compile graph with:

```python
graph = builder.compile(
    checkpointer=checkpointer
)
```

Every run must use a unique:

```text
thread_id = run_id
```

Example:

```python
config = {
    "configurable": {
        "thread_id": run_id
    }
}
```

Later consider persistent checkpoint storage only if required.

---

# 34. Research Contribution vs LangGraph Replay

Do not claim:

```text
"Our novelty is checkpoint replay."
```

LangGraph provides replay/checkpoint infrastructure.

The research algorithm decides **which node/subgraph became invalid** using:

```text
MCP provenance
+
resource versions
+
semantic conflict classification
+
dependency graph
```

LangGraph is only the recovery execution mechanism.

---

# 35. Selective Recovery Behavior

Example:

```text
A branch invalid
B branch valid
```

Required behavior:

```text
A_prepare   preserve if valid
A_reason    rerun
A_commit    rerun

B_prepare   preserve
B_reason    preserve
B_commit    preserve
```

Never discard B's output merely because A had a conflict in `dependency_occ`.

Track:

```text
rerun_node_count
preserved_node_count
```

---

# 36. Experimental Protocols

Use exactly these protocol identifiers:

```text
naive
2pl
occ
dependency_occ
```

Same scenario input must be reusable for all protocols.

---

# 37. Protocol: naive

Behavior:

```text
- no locks
- no version validation
- no recovery
```

Measure:

```text
fast execution
low coordination overhead
possible incorrect final state
```

---

# 38. Protocol: 2pl

Implement per-resource locks.

Start with:

```python
dict[str, asyncio.Lock]
```

For the experimental design, locks must cover:

```text
READ
+
LLM reasoning interval
+
WRITE
```

Do not release immediately after the read, because that would not model the pessimistic locking behavior the research compares against.

Measure:

```text
lock wait time
wall-clock latency
success
tokens
```

---

# 39. Protocol: occ

Behavior:

```text
run concurrently
validate versions
if conflict:
    abort affected run/branch completely
    discard prior reasoning
    restart from beginning
```

Track:

```text
retry_count
wasted_tokens
wasted_tool_calls
```

This is the full-restart OCC baseline.

---

# 40. Protocol: dependency_occ

Behavior:

```text
version mismatch
      |
      v
semantic auditor
      |
  non-disruptive?
   /          \
 yes          no
 |             |
continue    dependency graph
                |
                v
        affected subgraph
                |
                v
        selective re-execution
```

This is the proposed research method.

---

# 41. FastAPI API

Minimum endpoints:

```text
GET  /health
POST /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/logs
GET  /runs/{run_id}/dependencies
GET  /runs/{run_id}/conflicts
GET  /runs/{run_id}/graph
GET  /metrics
```

Optional development endpoints:

```text
GET  /resources
POST /resources/reset
```

---

# 42. POST /runs

Request:

```json
{
  "scenario_id": "inventory_001",
  "protocol": "dependency_occ"
}
```

Pydantic:

```python
class StartRunRequest(BaseModel):
    scenario_id: str

    protocol: Literal[
        "naive",
        "2pl",
        "occ",
        "dependency_occ",
    ]
```

Response example:

```json
{
  "run_id": "uuid",
  "scenario_id": "inventory_001",
  "protocol": "dependency_occ",
  "status": "completed",
  "success": true
}
```

---

# 43. Benchmark File

Use:

```text
benchmarks/scenarios.json
```

Initial scenario:

```json
[
  {
    "id": "inventory-critical-01",

    "initial_state": {
      "inventory/product_1": {
        "quantity": 100,
        "price": 20,
        "description": "Product A"
      }
    },

    "agent_a": {
      "task": "Allocate 80 units of product_1 to customer A."
    },

    "agent_b": {
      "task": "Reduce available quantity of product_1 to 50."
    },

    "delays": {
      "agent_a_after_read_ms": 2000,
      "agent_b_before_write_ms": 500
    },

    "semantic_ground_truth": "disruptive"
  }
]
```

Add a benign scenario later:

```json
{
  "id": "inventory-benign-01",

  "agent_a": {
    "task": "Allocate 50 units."
  },

  "agent_b": {
    "task": "Change the product description only."
  },

  "semantic_ground_truth": "non_disruptive"
}
```

---

# 44. Initial Benchmark Progression

Do not create 50 scenarios immediately.

Implement in this order:

```text
1. critical conflict
2. non-disruptive conflict
3. no conflict
4. five mixed scenarios
5. ten scenarios
6. final benchmark suite
```

Only expand after the pipeline is stable.

---

# 45. Required Metrics

Capture from the first working experiments:

```text
run_id
scenario_id
protocol

success

wall_clock_ms

prompt_tokens
completion_tokens
total_tokens

auditor_tokens

tool_call_count

conflict_count
semantic_conflict_count

retry_count

rerun_node_count
preserved_node_count

wasted_tokens

recovery_latency_ms
```

---

# 46. Semantic Auditor Evaluation

For manually labelled conflicts calculate:

```text
TP = disruptive correctly classified disruptive
TN = benign correctly classified non-disruptive
FP = benign incorrectly classified disruptive
FN = disruptive incorrectly classified non-disruptive
```

Metrics:

```text
Accuracy
Precision
Recall
F1
```

Keep these separate from overall workflow task success.

---

# 47. Benchmark Comparison Output

Eventually produce tables similar to:

| Metric | Naive | 2PL | OCC | Dependency OCC |
|---|---:|---:|---:|---:|
| Success rate | | | | |
| Mean latency | | | | |
| Mean total tokens | | | | |
| Mean wasted tokens | | | | |
| Conflicts | | | | |
| Mean nodes re-executed | | | | |
| Mean nodes preserved | | | | |

Also compare Semantic Auditor configurations separately.

---

# 48. Auditor Experiments

Support configuration of:

```text
worker model
auditor model
```

They do not have to be the same.

Later compare:

```text
small/cheap auditor
stronger auditor
improved prompt/structured-output auditor
```

Measure:

```text
accuracy
precision
recall
F1
auditor tokens
auditor latency
```

---

# 49. External Side Effects

For the BSc prototype, do not initially use irreversible operations such as:

```text
sending real emails
real payments
real external deletes
real infrastructure mutation
```

Use reversible controlled resources:

```text
SQLite records
JSON state
versioned files
inventory records
shared document state
```

Graph-state rollback does not automatically undo external side effects.

---

# 50. Logging Requirements

Use Python `logging`.

Every run should make it easy to inspect:

```text
run started
scenario loaded
worker A started
worker B started

A READ X@v1
B READ X@v1
B WRITE X v1->v2

A attempted WRITE expected v1
VERSION CONFLICT

semantic audit = disruptive

affected nodes:
- a_reason
- a_commit

replayed:
- a_reason
- a_commit

preserved:
- b_reason
- b_commit

run completed
```

Do not use `print()` for normal production/debug logging.

---

# 51. Coding Standards

Use:

- async-first design where relevant
- type hints
- Pydantic schemas at API boundaries
- small focused services
- dependency injection where appropriate
- docstrings on research-critical algorithms
- structured error responses
- deterministic test seeds where applicable
- no hidden global mutable state except intentionally managed locks/context variables

Prefer clear code over abstraction-heavy patterns.

---

# 52. Testing Strategy

Add tests in this order.

## Unit

```text
resource read
resource update
atomic version check
version conflict
provenance logging
dependency recording
dependency descendants
semantic schema validation
```

## Integration

```text
MCP read
MCP write
MCP OCC conflict
FastAPI health
POST /runs basic scenario
```

## Concurrency

Simulate two async workers:

```text
A reads v1
B writes v2
A attempts expected v1
```

This test must reliably produce a version conflict.

Do not require a real LLM for low-level OCC tests.

---

# 53. Mockable LLM Layer

Design workers and auditor so tests can replace the real LLM with deterministic mock/stub behavior.

Do not make database or concurrency tests depend on live LLM APIs.

Live LLM experiments belong in benchmark/integration tests.

---

# 54. Milestones

## Milestone 1 — Reproduce the Problem

Build only:

```text
FastAPI
   |
LangGraph
 /      \
A        B
 \      /
 shared MCP
    |
 SQLite
```

Target behavior:

```text
Agent A reads X@v1

Agent B writes:
X@v1 -> X@v2

Agent A attempts a write using expected v1

System detects:
VERSION CONFLICT
expected = 1
actual = 2
```

No Semantic Auditor yet.

No selective rollback yet.

---

## Milestone 2 — Semantic Classification

Add:

```text
version conflict
      |
      v
semantic auditor
      |
critical / non-disruptive
```

Acceptance:

- structured output
- manually-labelled benchmark cases
- confusion matrix possible

---

## Milestone 3 — Dependency Graph

Add:

```text
resource version
      |
      v
reasoning node
      |
      v
commit node
```

Acceptance:

- can identify descendants
- can return affected node set

---

## Milestone 4 — Selective Recovery

Add:

```text
disruptive conflict
       |
dependency scan
       |
affected nodes
       |
checkpoint/replay
```

Acceptance:

- affected branch re-runs
- valid sibling branch is preserved

---

## Milestone 5 — Four Baselines

Implement:

```text
naive
2pl
occ
dependency_occ
```

Acceptance:

- same benchmark can be run under all four
- metrics are stored for each run

---

## Milestone 6 — Benchmarking

Add multiple scenarios and repeated trials.

Produce:

```text
correctness
latency
token use
wasted tokens
retry counts
semantic F1
re-executed nodes
preserved nodes
```

---

# 55. Milestone 1 Codex Task

**Start here.**

Codex should first create only the base necessary for Milestone 1.

Implement:

1. Project structure.
2. `pyproject.toml`.
3. `.env.example`.
4. configuration model.
5. SQLite initialization.
6. resource repository.
7. atomic versioned writes.
8. provenance logging.
9. basic MCP server.
10. MCP read/write/list tools.
11. FastAPI `/health`.
12. unit tests for resource versioning and OCC conflicts.

Do **not** implement yet:

```text
Deep Agents
Semantic Auditor
NetworkX graph
Selective rollback
2PL
benchmark statistics
streaming UI
frontend
Docker
PostgreSQL
```

After Milestone 1 storage/MCP behavior is tested, proceed to:

```text
one Deep Agent
then two parallel LangGraph workers
```

---

# 56. Milestone 1 Acceptance Criteria

The base is considered correct only if:

### Health

```bash
curl http://localhost:8000/health
```

returns:

```json
{
  "status": "ok"
}
```

### Resource Test

Resource starts:

```text
X@v1
```

Write with:

```text
expected_version=1
```

must succeed and produce:

```text
X@v2
```

A second write using stale:

```text
expected_version=1
```

must fail with a structured `VersionConflict`.

### Atomicity

The version check and mutation occur in one SQL statement.

### Logging

Successful reads and writes create provenance records.

### MCP

MCP tool calls can:

```text
list resource
read resource + version
write resource with expected version
receive structured version-conflict result
```

### Tests

```bash
uv run pytest
```

must pass.

---

# 57. README Requirements

Generate a clear `README.md` containing:

```text
project purpose
architecture
setup instructions
how to run FastAPI
how to run MCP server
how to run tests
current milestone
future milestones
```

Also explicitly say:

> This system is a research prototype for dependency-aware optimistic concurrency control in concurrent LLM-agent workflows using MCP. LangGraph and Deep Agents provide orchestration and reasoning infrastructure; the research contribution is the MCP provenance, semantic conflict analysis, dependency-aware invalidation, and selective recovery mechanism.

---

# 58. Git Discipline

Use small commits conceptually aligned with milestones.

Suggested order:

```text
chore: initialize project structure

feat: add async sqlite storage

feat: add versioned shared resources

feat: add provenance logging

feat: add atomic occ validation

feat: expose shared state over mcp

feat: add fastapi control api

test: add resource and occ tests

feat: add first deep agent worker

feat: add parallel langgraph execution

feat: add semantic conflict auditor

feat: add dependency graph

feat: add selective recovery

feat: add experimental protocols

feat: add benchmark runner
```

---

# 59. Things Codex Must Not Do

Do not:

- replace versioned OCC with an in-memory-only check
- let the LLM invent `run_id`, `agent_id`, or `node_id`
- let workers bypass MCP for shared-state mutation
- restart all branches in `dependency_occ`
- hide all reasoning inside one opaque agent node
- confuse LangGraph checkpoint replay with the research contribution
- depend on random model latency to generate race conditions
- benchmark semantic classification without ground-truth labels
- use real irreversible side effects in the first prototype
- implement the entire final system before Milestone 1 tests pass
- add unnecessary enterprise infrastructure

---

# 60. Immediate Instruction to Codex

Use this exact instruction after loading this file:

```text
Read DEPENDENCY_AWARE_MCP_BUILD_SPEC.md completely.

We are starting with Milestone 1 only.

Inspect the current repository first.

Then scaffold and implement the Milestone 1 base described in the specification.

Requirements:
- Python 3.11+
- uv
- FastAPI
- async SQLite with aiosqlite
- MCP Python SDK v2
- atomic optimistic version validation
- provenance logging
- clean modular architecture
- tests

Do not implement Deep Agents, Semantic Auditor, dependency graph, selective rollback, 2PL, or benchmark statistics yet.

After making changes:
1. run the test suite,
2. report which files were created/changed,
3. explain any API/version assumptions,
4. identify the next smallest implementation step.
```

---

# 61. Definition of the Final Research Prototype

The completed system should eventually demonstrate:

```text
Concurrent Deep Agent workers
          |
          v
Shared MCP server
          |
          v
Versioned shared resources
          |
          v
Read/write provenance
          |
          v
Structural conflict detection
          |
          v
Semantic conflict classification
          |
          v
Dependency-aware invalidation
          |
          v
Selective LangGraph re-execution
```

and experimentally compare:

```text
Naive
vs
2PL
vs
Full-restart OCC
vs
Dependency-aware semantic OCC
```

using:

```text
task correctness
wall-clock latency
total tokens
wasted tokens
semantic-auditor accuracy/F1
number of retries
nodes re-executed
nodes preserved
```

The implementation should remain simple enough that every result can be explained in the BSc dissertation.
