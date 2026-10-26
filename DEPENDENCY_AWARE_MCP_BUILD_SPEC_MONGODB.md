# Dependency-Aware OCC for Multi-Agent MCP Systems
## Codex Build Specification — MongoDB Atlas Version

> **Primary implementation brief for Codex in VS Code**
>
> Build this project incrementally. Start with Milestone 1 only.
>
> **Database decision:** MongoDB Atlas is the persistent backend for the research prototype.
>
> The research goal is to evaluate whether **MCP read/write provenance + resource versioning + semantic conflict classification + dependency-aware selective re-execution** reduces wasted tokens and latency compared with full-restart optimistic concurrency control while preserving correctness.

---

# 1. Research Goal

Build a multi-agent system where multiple LLM workers concurrently interact with the same stateful MCP server.

The system must demonstrate this sequence:

1. Agent A reads a shared resource at version `v1`.
2. Agent B modifies the same shared resource and creates version `v2`.
3. Agent A continues reasoning using stale information from `v1`.
4. The system detects the structural version conflict.
5. A dedicated Semantic Auditor determines whether the change actually invalidates Agent A's reasoning.
6. If the conflict is semantically disruptive, the system identifies the affected LangGraph nodes.
7. Only the affected execution subgraph is re-executed.
8. Outputs from unaffected sibling agents/nodes are preserved.

The final experiment compares four protocols:

```text
naive
2pl
occ
dependency_occ
```

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
- MongoDB Atlas
- PyMongo Async API
- `networkx`
- `pydantic`
- `pydantic-settings`
- `python-dotenv`
- `httpx`
- `pytest`
- `pytest-asyncio`

Use `uv` for dependency management.

Use the official PyMongo async API:

```python
from pymongo import AsyncMongoClient
```

Do not use Motor for new code.

---

# 3. Architecture

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
           | 2PL Lock Manager           |
           +-------------+--------------+
                         |
                         v
                 MongoDB Atlas
```

Responsibilities:

```text
Deep Agents
= LLM reasoning workers

LangGraph
= execution topology, state, checkpointing, replay

FastAPI
= external control/API layer

MCP
= only shared-resource/tool access boundary exposed to workers

MongoDB Atlas
= persistent shared state + experiment records

Concurrency middleware
= provenance, versioning, OCC, lock management, conflict detection

Semantic Auditor
= semantic conflict classification

Dependency Graph
= downstream invalidation analysis

Recovery Router
= selective LangGraph re-execution
```

---

# 4. Critical Architectural Rule

Do not make the whole workflow one opaque Deep Agent.

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

Deep Agents may be invoked inside explicit LangGraph reasoning nodes.

---

# 5. MongoDB Must Stay Behind MCP

Required:

```text
Agent
  |
  v
MCP Tool
  |
  v
Concurrency Middleware
  |
  v
MongoDB
```

Forbidden:

```text
Agent -----------------> MongoDB
```

Workers must never receive MongoDB credentials.

---

# 6. Project Structure

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
│   │   ├── mongodb.py
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
│   ├── test_locks.py
│   └── test_api.py
│
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

---

# 7. Setup

```bash
mkdir dependency-aware-mcp
cd dependency-aware-mcp

uv init

uv add fastapi "uvicorn[standard]"
uv add deepagents langgraph
uv add "langchain[mcp]>=1.4"
uv add "mcp[cli]"
uv add pymongo
uv add networkx
uv add pydantic pydantic-settings python-dotenv
uv add httpx

uv add --dev pytest pytest-asyncio
```

Install one model provider separately.

---

# 8. Environment

`.env.example`

```env
MODEL=provider:model-name
AUDITOR_MODEL=provider:model-name

MONGODB_URI=mongodb+srv://USERNAME:PASSWORD@CLUSTER_HOST/?retryWrites=true&w=majority
MONGODB_DATABASE=dependency_aware_mcp

API_HOST=127.0.0.1
API_PORT=8000

MCP_HOST=127.0.0.1
MCP_PORT=8001
MCP_URL=http://127.0.0.1:8001/mcp
```

Never commit `.env`.

---

# 9. Collections

Use:

```text
resources
access_logs
dependencies
conflicts
runs
resource_locks
```

---

# 10. resources

```json
{
  "_id": "inventory/product_1",
  "value": {
    "quantity": 100,
    "price": 20,
    "description": "Product A"
  },
  "version": 1,
  "createdAt": "datetime",
  "updatedAt": "datetime"
}
```

Rules:

- `_id` is the stable resource key.
- `version` is an integer.
- every successful mutation increments `version`.
- mutation and version increment happen atomically in one MongoDB update.

---

# 11. access_logs

```json
{
  "_id": "ObjectId",
  "runId": "uuid-string",
  "agentId": "worker_a",
  "nodeId": "a_reason",
  "resourceKey": "inventory/product_1",
  "operation": "READ",
  "version": 4,
  "timestamp": "datetime"
}
```

Initial operation values:

```text
READ
WRITE
```

---

# 12. dependencies

```json
{
  "_id": "ObjectId",
  "runId": "uuid-string",
  "agentId": "worker_a",
  "nodeId": "a_reason",
  "resourceKey": "inventory/product_1",
  "readVersion": 4,
  "timestamp": "datetime"
}
```

Represents:

```text
a_reason depends on inventory/product_1@v4
```

---

# 13. conflicts

```json
{
  "_id": "ObjectId",
  "runId": "uuid-string",
  "agentId": "worker_a",
  "nodeId": "a_commit",
  "resourceKey": "inventory/product_1",
  "expectedVersion": 4,
  "actualVersion": 5,
  "semanticResult": null,
  "confidence": null,
  "affectedPremises": [],
  "timestamp": "datetime"
}
```

Later:

```text
semanticResult = disruptive | non_disruptive
```

---

# 14. runs

```json
{
  "_id": "run-uuid",
  "scenarioId": "inventory-critical-01",
  "protocol": "dependency_occ",
  "status": "running",
  "startedAt": "datetime",
  "completedAt": null,
  "success": null,
  "metrics": {
    "wallClockMs": 0,
    "promptTokens": 0,
    "completionTokens": 0,
    "totalTokens": 0,
    "auditorTokens": 0,
    "toolCallCount": 0,
    "conflictCount": 0,
    "semanticConflictCount": 0,
    "retryCount": 0,
    "rerunNodeCount": 0,
    "preservedNodeCount": 0,
    "wastedTokens": 0,
    "recoveryLatencyMs": 0,
    "lockWaitMs": 0
  }
}
```

---

# 15. resource_locks

Application-level pessimistic-locking baseline:

```json
{
  "_id": "inventory/product_1",
  "ownerRunId": "run-uuid",
  "ownerAgentId": "worker_a",
  "acquiredAt": "datetime",
  "expiresAt": "datetime"
}
```

This is the project's logical lock implementation.

Do not describe it as MongoDB's internal lock manager.

---

# 16. Indexes

Create indexes on startup.

`access_logs`:

```text
(runId, timestamp)
(runId, agentId)
(resourceKey, timestamp)
```

`dependencies`:

```text
(runId, resourceKey)
(runId, nodeId)
```

`conflicts`:

```text
(runId, timestamp)
(resourceKey, timestamp)
```

`runs`:

```text
(scenarioId, protocol)
(startedAt DESC)
```

`resource_locks`:

```text
_id
```

Optional TTL:

```text
expiresAt with expireAfterSeconds=0
```

Do not rely on TTL deletion for precise lock correctness.

---

# 17. Async MongoDB Client

Use:

```python
from pymongo import AsyncMongoClient
```

Create one client for the application lifecycle.

Example:

```python
from pymongo import AsyncMongoClient
from app.config import settings


class Mongo:
    client: AsyncMongoClient | None = None
    db = None


mongo = Mongo()


async def connect_mongodb() -> None:
    mongo.client = AsyncMongoClient(
        settings.mongodb_uri
    )
    mongo.db = mongo.client[
        settings.mongodb_database
    ]

    await mongo.client.admin.command("ping")


async def close_mongodb() -> None:
    if mongo.client is not None:
        await mongo.client.close()
```

Do not create a client per request.

---

# 18. Repository Layer

Create:

```text
ResourceRepository
ProvenanceRepository
ConflictRepository
RunRepository
LockRepository
```

FastAPI and MCP routes must call repositories/services.

Do not scatter raw MongoDB CRUD operations throughout the application.

---

# 19. Resource Read

Conceptual repository method:

```python
async def get_resource(resource_key: str) -> dict:
    document = await resources.find_one(
        {"_id": resource_key}
    )

    if document is None:
        raise ResourceNotFound(resource_key)

    return document
```

---

# 20. Atomic OCC Write

This is research-critical.

Never use:

```python
resource = await get_resource(resource_key)

if resource["version"] == expected_version:
    await update_resource(...)
```

Use one conditional MongoDB update.

Recommended:

```python
from pymongo import ReturnDocument

updated = await resources.find_one_and_update(
    {
        "_id": resource_key,
        "version": expected_version,
    },
    {
        "$set": {
            "value": new_value,
            "updatedAt": now,
        },
        "$inc": {
            "version": 1,
        },
    },
    return_document=ReturnDocument.AFTER,
)
```

Critical filter:

```python
{
    "_id": resource_key,
    "version": expected_version
}
```

If `updated is None`, the write lost the OCC race.

That is a version conflict.

---

# 21. OCC Example

Start:

```text
X@v4
```

A reads:

```text
X@v4
```

B reads:

```text
X@v4
```

B writes first:

```text
filter version=4
success
X@v5
```

A writes:

```text
filter version=4
no match
```

Result:

```text
VERSION CONFLICT
expected=4
actual=5
```

---

# 22. Get Actual Version After Conflict

After the conditional update fails:

```python
current = await resources.find_one(
    {"_id": resource_key},
    {"version": 1},
)
```

This second read is diagnostic only.

The conflict has already been determined by the atomic failed conditional update.

---

# 23. Exceptions

Create:

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
        self.resource_key = resource_key
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Version conflict for {resource_key}: "
            f"expected={expected_version}, "
            f"actual={actual_version}"
        )


class LockUnavailable(Exception):
    pass
```

---

# 24. Provenance

Implement:

```python
async def log_read(...)
async def log_write(...)
async def record_dependency(...)
async def record_conflict(...)
```

A successful read must create:

```text
access_logs
dependencies
```

A successful write must create:

```text
access_logs
```

A stale write must create:

```text
conflicts
```

---

# 25. Transactions

Do not wrap everything in a MongoDB transaction.

For Milestone 1, the research-critical atomicity is the resource's single-document conditional update.

Use multi-document transactions later only when a group of writes truly needs atomicity.

If used, use async sessions and do not perform parallel operations inside one transaction/session.

---

# 26. MCP Server

Use MCP Python SDK v2.

```python
from mcp.server import MCPServer

mcp = MCPServer(
    "Dependency Aware Shared State"
)
```

Initially run separately from FastAPI.

Target:

```text
http://127.0.0.1:8001/mcp
```

Use Streamable HTTP.

---

# 27. MCP Tools

Minimum:

```text
read_shared_resource
write_shared_resource
list_shared_resources
```

Do not expose raw MongoDB CRUD operations.

---

# 28. MCP Read Tool

Model-facing:

```python
read_shared_resource(
    resource_key: str
)
```

The model does not supply:

```text
run_id
agent_id
node_id
```

Runtime injects those values.

Behavior:

```text
fetch MongoDB resource
log READ
record dependency
return value + version
```

Example:

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

# 29. MCP Write Tool

Model-facing:

```python
write_shared_resource(
    resource_key: str,
    new_value: dict,
    expected_version: int
)
```

Behavior in Milestone 1:

```text
attempt atomic versioned write
        |
      match?
      /    \
    yes     no
    |        |
 version++  conflict record
    |        |
 log write  structured conflict response
```

Successful response:

```json
{
  "status": "ok",
  "resource_key": "inventory/product_1",
  "previous_version": 3,
  "version": 4
}
```

Conflict:

```json
{
  "status": "conflict",
  "resource_key": "inventory/product_1",
  "expected_version": 3,
  "current_version": 4
}
```

The MCP tool must not restart LangGraph.

---

# 30. Runtime Identity

Use `ContextVar`.

```python
from contextvars import ContextVar

current_run_id = ContextVar("current_run_id")
current_agent_id = ContextVar("current_agent_id")
current_node_id = ContextVar("current_node_id")
current_protocol = ContextVar("current_protocol")
```

The model must never provide trusted provenance identity.

---

# 31. Test MongoDB First

Before MCP:

1. connect to Atlas;
2. `ping`;
3. create resource;
4. read `v1`;
5. conditional write expected `v1`;
6. verify `v2`;
7. stale conditional write expected `v1`;
8. verify conflict;
9. verify resource remained `v2`;
10. verify indexes.

---

# 32. Test MCP Before Agents

Then:

1. start MCP;
2. call list;
3. call read;
4. verify access log;
5. verify dependency;
6. call correct-version write;
7. verify version increment;
8. call stale write;
9. verify structured conflict.

Do not add Deep Agents before this works.

---

# 33. FastAPI

Implement:

```text
GET /health
```

Response:

```json
{
  "status": "ok",
  "mongodb": "connected"
}
```

Do not return MongoDB credentials or host details.

Use FastAPI lifespan for:

```text
connect MongoDB
create indexes
later connect MCP adapter
later build workers
later compile LangGraph
yield
close resources
```

---

# 34. Deep Agent Workers

After Milestone 1:

```python
from deepagents import create_deep_agent
```

Create two independent workers.

Do not call one shared stateful worker instance concurrently.

System instructions:

```text
Use MCP shared-resource tools.
Remember versions returned by reads.
Use the relevant read version as expected_version when writing.
Never invent versions.
Never bypass MCP for shared state.
```

---

# 35. Parallel LangGraph

First agent graph:

```text
        START
       /     \
worker_a     worker_b
       \     /
         join
          |
         END
```

Acceptance:

- both workers overlap in time;
- both access the same MCP server;
- both ultimately access the same MongoDB resources;
- contexts remain independent.

---

# 36. Forced Race Conditions

Do not rely on random LLM timing.

Scenario example:

```json
{
  "scenario_id": "inventory_001",
  "delays": {
    "agent_a_after_read_ms": 2000,
    "agent_b_before_write_ms": 500
  }
}
```

Target:

```text
A: READ X@v1 -------- reasoning -------- WRITE expected v1

B:          READ X@v1 -> WRITE X@v2

                                      conflict
```

Implement delay hooks outside the LLM.

---

# 37. Structural Conflict Detection

For each dependency:

```text
readVersion
vs
current resource version
```

If:

```text
current > readVersion
```

record a candidate stale dependency.

Important:

```text
version mismatch != semantic invalidation
```

---

# 38. Semantic Auditor

Dedicated node/model.

Schema:

```python
class SemanticConflictDecision(BaseModel):
    disruptive: bool
    affected_premises: list[str]
    reason: str
    confidence: float
```

Input:

```text
task
worker output
old resource value
old version
new resource value
new version
changed fields
node ID
```

---

# 39. Benign Conflict Example

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

Worker decision:

```text
Allocate 50 units.
```

Expected:

```text
structural conflict = yes
semantic disruption = no
```

---

# 40. Ground Truth

Every conflict benchmark must include:

```text
disruptive
or
non_disruptive
```

Calculate:

```text
Accuracy
Precision
Recall
F1
```

---

# 41. Dependency Graph

Use:

```python
import networkx as nx
G = nx.DiGraph()
```

Example:

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

On disruptive conflict:

```python
affected = {
    "a_reason",
    *nx.descendants(G, "a_reason"),
}
```

---

# 42. Target LangGraph

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

# 43. LangGraph Checkpointing

Development:

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
```

Use:

```python
config = {
    "configurable": {
        "thread_id": run_id
    }
}
```

LangGraph replay is infrastructure.

The research contribution is deciding **what became invalid and what must be replayed**.

---

# 44. Selective Recovery

If A is invalid and B is valid:

```text
A_prepare   preserve if independent
A_reason    rerun
A_commit    rerun

B_prepare   preserve
B_reason    preserve
B_commit    preserve
```

Record:

```text
rerunNodeCount
preservedNodeCount
```

---

# 45. Protocols

Exact values:

```text
naive
2pl
occ
dependency_occ
```

---

# 46. Naive

```text
no logical resource lock
no expected-version validation
no semantic recovery
```

Still log provenance for evaluation.

---

# 47. 2PL Baseline

Use `resource_locks`.

Hold lock across:

```text
read
LLM reasoning
write
```

This intentionally measures long lock duration.

Acquire by unique insert on resource `_id`.

Release only with owner identity match.

Do not call this MongoDB's internal 2PL implementation.

Describe it as an **application-level pessimistic locking baseline**.

---

# 48. Lock Safety

Document:

```json
{
  "_id": "inventory/product_1",
  "ownerRunId": "...",
  "ownerAgentId": "worker_a",
  "acquiredAt": "...",
  "expiresAt": "..."
}
```

Optional TTL index cleans abandoned locks.

Correctness must use explicit ownership checks and explicit release.

---

# 49. Full-Restart OCC

Concurrent execution.

Conditional version update.

On conflict:

```text
abort
discard prior work
restart affected full workflow/branch from defined baseline start
```

No semantic filtering.

Track:

```text
retryCount
wastedTokens
wastedToolCalls
latency
```

---

# 50. Dependency-Aware OCC

```text
version conflict
      |
semantic auditor
      |
 disruptive?
 /         \
no         yes
|            |
continue   dependency graph
               |
        affected subgraph
               |
        selective replay
```

---

# 51. FastAPI Endpoints

Minimum:

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

Development/admin:

```text
GET  /resources
POST /resources/reset
```

Workers still use MCP for shared state.

---

# 52. POST /runs

Request:

```json
{
  "scenario_id": "inventory-critical-01",
  "protocol": "dependency_occ"
}
```

Response:

```json
{
  "run_id": "uuid",
  "scenario_id": "inventory-critical-01",
  "protocol": "dependency_occ",
  "status": "completed",
  "success": true
}
```

---

# 53. Benchmark Scenario

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

---

# 54. Metrics

Record:

```text
runId
scenarioId
protocol

success
wallClockMs

promptTokens
completionTokens
totalTokens
auditorTokens

toolCallCount

conflictCount
semanticConflictCount

retryCount

rerunNodeCount
preservedNodeCount

wastedTokens

recoveryLatencyMs
lockWaitMs
```

---

# 55. Auditor Metrics

```text
TP
TN
FP
FN
Accuracy
Precision
Recall
F1
```

Keep separate from workflow success.

---

# 56. Testing

Unit:

```text
resource creation
resource read
atomic version update
version increment
stale write conflict
access log
dependency record
conflict record
lock acquire
lock ownership
lock release
```

Integration:

```text
Atlas connection
MCP read
MCP write
MCP stale write
FastAPI health
```

Concurrency:

```text
A reads v1
B reads v1
B writes v2
A attempts expected v1
A gets conflict
```

No live LLM required for low-level concurrency tests.

---

# 57. Test Database

Use:

```text
dependency_aware_mcp_test
```

Never clean the main research database from test fixtures.

---

# 58. Milestone 1 — Build This First

Implement only:

1. project structure;
2. `pyproject.toml`;
3. `.env.example`;
4. settings;
5. `AsyncMongoClient`;
6. startup `ping`;
7. indexes;
8. resource repository;
9. versioned resources;
10. atomic OCC update;
11. access logs;
12. dependency records;
13. conflict records;
14. MCP server;
15. MCP read/list/write tools;
16. FastAPI `/health`;
17. tests.

Do not implement yet:

```text
Deep Agents
Semantic Auditor
NetworkX dependency graph
selective replay
2PL baseline
benchmark statistics
frontend
Docker
```

---

# 59. Milestone 1 Acceptance

Initial:

```json
{
  "_id": "inventory/product_1",
  "value": {
    "quantity": 100
  },
  "version": 1
}
```

Write:

```text
expectedVersion=1
quantity=80
```

must produce:

```text
version=2
quantity=80
```

Second stale write:

```text
expectedVersion=1
quantity=60
```

must produce:

```text
VERSION CONFLICT
expected=1
actual=2
```

Resource must remain:

```text
version=2
quantity=80
```

---

# 60. Milestone Sequence

```text
Milestone 1:
MongoDB + MCP base

Milestone 2:
one Deep Agent connected to MCP

Milestone 3:
two parallel LangGraph workers + forced race

Milestone 4:
Semantic Auditor

Milestone 5:
dependency graph

Milestone 6:
selective recovery

Milestone 7:
naive / 2pl / occ / dependency_occ

Milestone 8:
benchmarking and statistics
```

---

# 61. README

Include:

- research purpose;
- architecture;
- MongoDB Atlas setup;
- environment variables;
- how to run FastAPI;
- how to run MCP;
- how to run tests;
- current milestone;
- future milestones.

Include this statement:

> This repository is a research prototype for dependency-aware optimistic concurrency control in concurrent LLM-agent workflows using MCP. LangGraph and Deep Agents provide orchestration and reasoning infrastructure. MongoDB Atlas stores shared versioned resources and experimental provenance. The research contribution is the MCP provenance, semantic conflict analysis, dependency-aware invalidation, and selective recovery mechanism.

---

# 62. Things Codex Must Not Do

Do not:

- add SQLite;
- add PostgreSQL;
- use Motor;
- create a MongoDB client per request;
- implement OCC as read/check/write;
- expose MongoDB credentials to agents;
- let agents connect directly to MongoDB;
- trust LLM-provided run/agent/node identity;
- let workers bypass MCP;
- depend on random LLM latency;
- claim MongoDB internal locks are the project's 2PL;
- rerun all branches in `dependency_occ`;
- hide the whole graph inside one Deep Agent;
- call LangGraph replay the research novelty;
- use irreversible real-world side effects initially;
- implement later milestones before Milestone 1 tests pass.

---

# 63. Immediate Codex Prompt

```text
Read DEPENDENCY_AWARE_MCP_BUILD_SPEC_MONGODB.md completely.

We have chosen MongoDB Atlas as the database.

Start with Milestone 1 only.

Before changing code:
1. inspect the existing repository;
2. reuse working code where appropriate;
3. do not remove working code unnecessarily.

Implement the Milestone 1 MongoDB + MCP base.

Use:
- Python 3.11+
- uv
- FastAPI
- PyMongo Async API with AsyncMongoClient
- MongoDB Atlas
- MCP Python SDK v2
- atomic conditional version updates
- provenance logging
- dependency records
- structured version conflicts
- repository/service separation
- pytest

Important:
- MongoDB must be accessed only by backend/repository code.
- worker shared state must later be exposed only through MCP.
- OCC must use one conditional MongoDB update containing the expected version.
- do not implement check-then-update OCC.
- use one AsyncMongoClient for the application lifecycle.
- do not use Motor.
- do not implement Deep Agents yet.
- do not implement Semantic Auditor yet.
- do not implement NetworkX dependency graph yet.
- do not implement selective rollback yet.
- do not implement the 2PL baseline yet.
- do not add Docker or a frontend.

After implementing:
1. run the test suite;
2. report files created/changed;
3. report test results;
4. explain collections and indexes;
5. show the atomic OCC implementation;
6. identify the next smallest implementation step.
```

---

# 64. Final Prototype Definition

```text
Concurrent Deep Agent workers
          |
          v
LangGraph execution graph
          |
          v
Shared MCP server
          |
          v
MCP read/write provenance
          |
          v
MongoDB versioned resources
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

Compare:

```text
Naive
vs
application-level pessimistic locking
vs
full-restart OCC
vs
dependency-aware semantic OCC
```

Measure:

```text
task correctness
wall-clock latency
total tokens
wasted tokens
lock wait
semantic precision/recall/F1
retry count
nodes rerun
nodes preserved
```

---

# 65. Final Research Principle

Every experimental conflict should be explainable:

```text
Who read the resource?
Which version did they read?
Which node used it?
Who changed the resource?
Which version replaced it?
Was the change semantically relevant?
Which downstream nodes became invalid?
Which nodes were replayed?
Which nodes were preserved?
How much token/time cost was saved?
```

If the system can answer those questions reproducibly, the prototype is suitable for the proposed BSc evaluation.
