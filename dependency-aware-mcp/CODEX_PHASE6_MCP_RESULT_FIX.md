# Dependency-Aware MCP Research Project — Current Status and Repair Task for Codex

## Purpose

This document is for VS Code Codex.

The project is a BSc research prototype for:

> Dependency-Aware Optimistic Concurrency Control for Shared Context Synchronization in Multi-Agent MCP Ecosystems

The current implementation has already progressed through the main architecture phases. The immediate task is **not to redesign the system**. The immediate task is to **inspect the existing repository, locate the current MCP result-parsing issue, fix it safely, run the tests, and only then rerun the Phase 6 smoke benchmark**.

Repository path used during development:

```text
D:\Research\MAS-research\dependency-aware-mcp
```

Use the existing repository. Reuse the existing code where possible. Do not create a second implementation of the whole system.

---

# 1. Current Research Architecture

The intended architecture is:

```text
Client / Benchmark Harness
          |
          v
      LangGraph
      /       \
Worker A     Worker B
  |             |
  +------ MCP --+
          |
          v
Concurrency Middleware
          |
          +--> resource versioning
          +--> OCC validation
          +--> access logs
          +--> dependency logs
          +--> conflict records
          |
          v
      MongoDB Atlas
          |
          v
 Semantic Auditor
          |
   disruptive / non-disruptive
          |
          v
 Dependency Graph
          |
          v
 Recovery Router
    /           \
 rebase      selective rerun
```

The project uses:

- Python
- `uv`
- Ollama locally
- LangChain
- Deep Agents
- LangGraph
- MCP / FastMCP client
- MongoDB Atlas
- PyMongo Async API
- NetworkX
- pandas / scikit-learn for evaluation

---

# 2. Completed Development Phases

## Phase 1 — Multi-Agent + MCP

Implemented and tested conceptually:

```text
Worker A ----\
              ---> MCP ---> MongoDB
Worker B ----/
```

The system reproduced a stale-write race:

```text
A reads v1
B reads v1
B writes v2
A tries write with expected_version=v1
=> VERSION CONFLICT
```

---

## Phase 2 — Concurrency Middleware + Provenance

Added:

- `access_logs`
- `dependencies`
- `conflicts`
- run IDs
- agent IDs
- LangGraph node IDs
- HTTP trace headers
- server-side MCP request context

Trace metadata is supplied by the orchestration layer, not by the LLM.

Typical trace fields:

```json
{
  "runId": "...",
  "agentId": "worker_a",
  "nodeId": "a_read",
  "resourceKey": "inventory/product_1",
  "operation": "READ",
  "version": 1
}
```

---

## Phase 3 — Semantic Auditor

Added an independent Ollama-powered Semantic Auditor.

It classifies structural version conflicts as:

```text
disruptive
```

or:

```text
non_disruptive
```

The Auditor uses:

- worker purpose
- stale/old resource state
- current resource state
- attempted stale write
- changed fields
- intended changes

It stores:

```text
semanticResult
confidence
affectedPremises
semanticReason
changedFields
intendedChanges
auditorModel
```

---

## Phase 4 — Dependency Graph + Selective Recovery

Added:

- NetworkX dependency graph
- affected node discovery
- preserved node discovery
- recovery router
- non-disruptive rebase
- disruptive selective rerun

Expected behavior:

### Non-disruptive conflict

```text
B changes quantity
A changes only price
Auditor => non_disruptive
=> rebase A's intended field onto current resource
```

### Disruptive conflict

```text
A plans allocation from stale quantity
B changes quantity
Auditor => disruptive
=> preserve unaffected work
=> rerun only A's dependent branch
```

---

## Phase 5 — Baseline Protocols

Added four protocol modes:

```text
1. naive
2. application-level 2PL-style locking
3. full-restart OCC
4. dependency-aware semantic OCC
```

The baseline MCP tools include or are expected to include:

```text
read_shared_resource
write_shared_resource
naive_write_shared_resource
acquire_resource_lock
release_resource_lock
locked_write_shared_resource
list_shared_resources
```

---

## Phase 6 — Evaluation Harness

The current evaluation design includes:

- common benchmark scenarios
- same Ollama worker model
- worker preparation stage
- worker decision stage
- protocol comparison
- MongoDB benchmark result storage
- token usage
- wasted tokens
- conflicts
- retries
- lock wait
- nodes reexecuted
- nodes preserved
- semantic prediction
- semantic ground truth
- CSV exports

Important expected result files:

```text
benchmark_results.csv
benchmark_summary.csv
benchmark_scenario_summary.csv
```

---

# 3. Current Immediate Problem

The latest 16-run smoke benchmark failed for all protocols.

The failure is not currently protocol-specific.

The repeated errors are:

```text
Unexpected MCP tool result: None
```

and:

```text
Unexpected MCP result: None
```

The current benchmark output therefore incorrectly shows values such as:

```text
correct = False
tokens = 0
conflicts = 0
finalValue = None
finalVersion = None
```

These benchmark results must NOT be used for research conclusions.

The most likely current failure point is code that assumes:

```python
result.data
```

always contains the dictionary returned by an MCP tool.

In the current FastMCP/MCP client path, `result.data` can be `None` while usable output may exist in:

```python
result.structured_content
```

or:

```python
result.content
```

Therefore, the repository needs one centralized MCP result extraction function.

---

# 4. Main Codex Task

## Goal

Inspect the existing repository and fix MCP tool result extraction so every raw MCP call can reliably obtain the dictionary returned by the MCP server.

Do NOT redesign the architecture.

Do NOT rewrite the project from scratch.

Do NOT bypass MCP by reading MongoDB directly inside protocol logic.

All agent/shared-state operations must continue through:

```text
worker / orchestration
        |
        v
       MCP
        |
        v
concurrency middleware
        |
        v
     MongoDB
```

Direct MongoDB access is acceptable only for:

- test setup/reset
- ground-truth verification
- benchmark result storage
- repository-level internal storage

---

# 5. Files to Inspect First

Inspect these existing files before changing anything:

```text
app/mcp_client/traced_tools.py
app/protocols/baselines.py
app/evaluation/runner.py
app/concurrency/recovery_service.py
app/graph/phase4.py
app/mcp_server/server.py
```

Also inspect:

```text
app/concurrency/middleware.py
app/evaluation/worker.py
app/evaluation/schemas.py
app/evaluation/scenarios.py
app/evaluation/metrics.py
app/storage/mongodb.py
app/storage/repositories.py
scripts/run_phase6_benchmark.py
scripts/summarize_phase6.py
```

Do not assume these files exactly match an earlier draft. Inspect the repository first and modify the actual current code.

---

# 6. Required Central MCP Result Extractor

## File

```text
app/mcp_client/traced_tools.py
```

## Action

If a reusable result extractor does not already exist, add one.

Use the following behavior.

```python
import json


def extract_tool_data(result) -> dict:
    """
    Extract a dictionary returned by an MCP tool.

    Preferred extraction order:

    1. result.data
    2. result.structured_content
    3. JSON stored in result.content TextContent blocks

    Raise a diagnostic RuntimeError when no dictionary can
    be recovered.
    """

    data = getattr(result, "data", None)

    if isinstance(data, dict):
        return data

    structured = getattr(
        result,
        "structured_content",
        None,
    )

    if isinstance(structured, dict):

        if (
            len(structured) == 1
            and "result" in structured
            and isinstance(
                structured["result"],
                dict,
            )
        ):
            return structured["result"]

        return structured

    content = getattr(
        result,
        "content",
        None,
    )

    if content:

        for block in content:

            text = getattr(
                block,
                "text",
                None,
            )

            if not text:
                continue

            try:
                parsed = json.loads(text)

            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):

                if (
                    len(parsed) == 1
                    and "result" in parsed
                    and isinstance(
                        parsed["result"],
                        dict,
                    )
                ):
                    return parsed["result"]

                return parsed

    raise RuntimeError(
        "MCP tool returned no usable dictionary. "
        f"data={getattr(result, 'data', None)!r}, "
        f"structured_content="
        f"{getattr(result, 'structured_content', None)!r}, "
        f"content={getattr(result, 'content', None)!r}"
    )
```

If the installed FastMCP version exposes a slightly different result structure, inspect the actual runtime object and adapt this extractor minimally.

Do not silently swallow invalid results.

---

# 7. Remove Duplicate MCP Result Parsing

Search the repository for patterns like:

```python
result.data
```

and local helpers such as:

```python
def tool_data(...)
```

or code that raises:

```text
Unexpected MCP result: None
```

or:

```text
Unexpected MCP tool result: None
```

Replace duplicate parsing logic with the shared:

```python
extract_tool_data(...)
```

At minimum inspect and fix:

```text
app/protocols/baselines.py
app/evaluation/runner.py
app/concurrency/recovery_service.py
app/graph/phase4.py
```

Do not replace uses of `.data` that are unrelated to MCP tool-call results.

---

# 8. Ensure `traced_tools.py` Has No Duplicate Function Definitions

Inspect:

```text
app/mcp_client/traced_tools.py
```

There must be only one definition of:

```python
traced_mcp_tools(...)
```

and one definition of:

```python
traced_mcp_client(...)
```

The intended structure is:

```python
imports

extract_tool_data(...)

_trace_headers(...)

traced_mcp_tools(...)

traced_mcp_client(...)
```

The trace headers should still include:

```text
X-Research-Run-Id
X-Research-Agent-Id
X-Research-Node-Id
```

---

# 9. Add / Verify a Dedicated MCP Result Diagnostic Test

## File

```text
scripts/test_mcp_result_format.py
```

## Action

Create it if it does not exist.

It must:

1. create a traced raw MCP client
2. call `read_shared_resource`
3. print:
   - `result.data`
   - `result.structured_content`
   - `result.content`
4. call `extract_tool_data(result)`
5. print the extracted dictionary
6. fail clearly if extraction fails

Suggested implementation:

```python
import asyncio
from uuid import uuid4

from app.mcp_client.traced_tools import (
    extract_tool_data,
    traced_mcp_client,
)


async def main() -> None:

    run_id = str(uuid4())

    async with traced_mcp_client(
        run_id=run_id,
        agent_id="debug_agent",
        node_id="debug_read",
    ) as client:

        result = await client.call_tool(
            "read_shared_resource",
            {
                "resource_key":
                    "inventory/product_1"
            },
        )

        print("\nRAW MCP RESULT")

        print(
            "data:",
            getattr(
                result,
                "data",
                None,
            ),
        )

        print(
            "structured_content:",
            getattr(
                result,
                "structured_content",
                None,
            ),
        )

        print(
            "content:",
            getattr(
                result,
                "content",
                None,
            ),
        )

        data = extract_tool_data(
            result
        )

        print("\nEXTRACTED RESULT")

        print(data)

        assert (
            data.get("status")
            == "ok"
        )

        assert (
            data.get(
                "resource_key"
            )
            == "inventory/product_1"
        )

        assert "value" in data

        assert "version" in data


if __name__ == "__main__":
    asyncio.run(main())
```

---

# 10. Validation Order

Do not immediately rerun the full benchmark.

Run tests in this order.

## 10.1 Configuration

From the repository root:

```powershell
uv run python -m scripts.test_config
```

If this file exists.

Expected:

- MongoDB settings load
- Ollama model loads from `.env`
- MCP URL loads

---

## 10.2 Ollama tool calling

```powershell
uv run python -m scripts.test_ollama_tools
```

Expected:

```text
response.tool_calls
```

must contain a real tool call.

---

## 10.3 MongoDB seed

```powershell
uv run python -m scripts.seed_resource
```

Expected resource:

```json
{
  "_id": "inventory/product_1",
  "value": {
    "quantity": 100,
    "price": 20,
    "description": "Test Product"
  },
  "version": 1
}
```

---

## 10.4 Start MCP server

In a separate terminal:

```powershell
uv run python -m app.mcp_server.server
```

Keep it running.

---

## 10.5 MCP result format diagnostic

```powershell
uv run python -m scripts.test_mcp_result_format
```

This test must pass before continuing.

The final extracted dictionary should look approximately like:

```python
{
    "status": "ok",
    "resource_key": "inventory/product_1",
    "value": {
        "quantity": 100,
        "price": 20,
        "description": "Test Product",
    },
    "version": 1,
}
```

The exact raw result representation may differ.

---

## 10.6 Existing MCP test

```powershell
uv run python -m scripts.test_mcp
```

Verify expected tools are exposed.

Expected tool names include:

```text
read_shared_resource
write_shared_resource
naive_write_shared_resource
acquire_resource_lock
release_resource_lock
locked_write_shared_resource
list_shared_resources
```

If the exact list differs, inspect why.

---

# 11. Then Run the Corrected Phase 6 Smoke Benchmark

Only after the tests above pass:

```powershell
uv run python -m scripts.run_phase6_benchmark
```

Keep:

```python
repetitions = 2
```

for now.

Do NOT increase repetitions.

Expected:

```text
2 scenarios
x 4 protocols
x 2 repetitions
= 16 runs
```

---

# 12. Required Phase 6 Scenarios

Inspect:

```text
app/evaluation/scenarios.py
```

The smoke benchmark should include these two conceptual scenarios.

---

## Scenario A — Non-Disruptive Independent Fields

Initial:

```json
{
  "quantity": 100,
  "price": 20,
  "description": "Test Product"
}
```

Worker B:

```text
set quantity = 60
```

Worker A:

```text
set price = 25
```

Correct final state:

```json
{
  "quantity": 60,
  "price": 25,
  "description": "Test Product"
}
```

Semantic ground truth:

```text
non_disruptive
```

---

## Scenario B — Disruptive Inventory Allocation

Initial:

```text
quantity = 100
```

Worker B:

```text
set quantity = 60
```

Worker A task:

```text
allocate exactly 30 units from CURRENT inventory
```

A's stale calculation from v1:

```text
100 - 30 = 70
```

After B's change, correct recalculation:

```text
60 - 30 = 30
```

Correct final state:

```json
{
  "quantity": 30,
  "price": 20,
  "description": "Test Product"
}
```

Semantic ground truth:

```text
disruptive
```

---

# 13. Verify Baselines Are Scenario-Aware

This was an earlier benchmark bug.

Inspect:

```text
app/protocols/baselines.py
```

The baseline functions must accept the current scenario.

Expected signatures are conceptually:

```python
run_naive(
    run_id=...,
    scenario=...,
)
```

```python
run_2pl(
    run_id=...,
    scenario=...,
)
```

```python
run_occ_full_restart(
    run_id=...,
    scenario=...,
)
```

They must NOT hard-code only:

```python
price = 25
quantity = 60
```

for every scenario.

They must use:

```python
scenario.worker_a_task
scenario.worker_b_task
scenario.expected_final
```

and the common benchmark worker.

---

# 14. Verify Common LLM Worker Usage

Inspect:

```text
app/evaluation/worker.py
```

All protocols should use the same Ollama worker process where appropriate:

```text
prepare
  |
  v
read
  |
  v
decide
  |
  v
protocol-specific commit
```

Expected common model configuration:

```python
ChatOllama(
    model=settings.ollama_model,
    base_url=settings.ollama_base_url,
    temperature=0,
)
```

Do not give one protocol a significantly easier reasoning path unless it is inherent to the protocol.

---

# 15. Verify Token Accounting

The previous benchmark had all token values as zero because execution failed before model work completed.

After the MCP extraction fix, inspect that token accounting works.

Expected per-run fields:

```text
inputTokens
outputTokens
totalTokens
wastedTokens
```

Do not invent token values.

Use actual Ollama / LangChain usage metadata when available.

---

# 16. Wasted Token Definitions

Use the following definitions consistently.

## Naive

```text
wastedTokens = 0
```

Nothing is intentionally discarded, even if the final state is wrong.

---

## 2PL

```text
wastedTokens = 0
```

Work waits instead of being aborted.

---

## Full-Restart OCC

When Worker A's first transaction conflicts:

```text
A_prepare
A_read
A_decide
A_commit
```

the full transaction restarts.

At minimum, the discarded LLM work should count as wasted.

If the implementation models preparation and decision as LLM calls:

```text
wastedTokens =
initial A preparation tokens
+
initial stale A decision tokens
```

---

## Dependency-Aware OCC — Non-Disruptive

If the Auditor decides:

```text
non_disruptive
```

the old reasoning is still valid.

Expected:

```text
wastedTokens = 0
```

and the current resource can be safely rebased.

---

## Dependency-Aware OCC — Disruptive

If the Auditor decides:

```text
disruptive
```

A's stale state-dependent reasoning is invalid.

But resource-independent preparation may still be valid.

Expected conceptual behavior:

```text
A_prepare       preserved
A_read          rerun
A_decide        rerun
A_commit        rerun
```

Therefore wasted tokens should normally include only the stale state-dependent LLM reasoning, not automatically all prior A tokens.

---

# 17. Node Metrics

Do not confuse:

```text
affected nodes
```

with:

```text
actually reexecuted nodes
```

Track separately:

```text
affectedNodes
nodesReexecuted
nodesPreserved
```

For example:

## Benign rebase

Affected nodes might be:

```text
a_read
a_stale_write
```

but actual LLM reasoning may not need rerun.

Therefore do NOT automatically set:

```python
nodes_reexecuted = len(affected_nodes)
```

---

## Disruptive selective recovery

Conceptually:

```text
recover_a_read
recover_a_decide
recover_a_commit
```

may mean:

```text
nodesReexecuted = 3
```

while unaffected Worker B work remains preserved.

---

# 18. Correctness Must Be Independently Verified

Every protocol run must be checked against:

```python
scenario.expected_final
```

using the final resource stored in MongoDB.

Do not trust an internal `protocol_result.correct` field without this final comparison.

Conceptually:

```python
correct = (
    final_resource["value"]
    == scenario.expected_final
)
```

This previously caught a bug where 2PL/OCC were running the wrong task but being marked correct.

---

# 19. Expected Smoke Benchmark Behavior

These are expected conceptual outcomes, not values to hard-code.

## Scenario A — Independent Fields

Expected:

```text
Naive:
likely incorrect due to lost update

2PL:
correct

Full OCC:
correct

Dependency OCC:
correct
semantic = non_disruptive
recovery = rebase
```

Correct final:

```text
quantity = 60
price = 25
```

---

## Scenario B — Inventory Allocation

Expected:

```text
Naive:
likely incorrect because A uses stale quantity

2PL:
correct if B serializes before A

Full OCC:
correct after restart

Dependency OCC:
correct
semantic = disruptive
selective recovery
```

Correct final:

```text
quantity = 30
price = 20
```

---

# 20. After the 16 Runs

Run:

```powershell
uv run python -m scripts.summarize_phase6
```

The summary should read only the latest completed benchmark.

Expected output files:

```text
benchmark_results.csv
benchmark_summary.csv
benchmark_scenario_summary.csv
```

---

# 21. What to Check in the New CSV Files

Before increasing repetitions, verify all of the following.

## Correctness

```text
2PL disruptive scenario:
final quantity = 30

OCC disruptive scenario:
final quantity = 30

Dependency OCC disruptive:
final quantity = 30
```

---

## Tokens

Token values should not all be zero.

Expected:

```text
totalTokens > 0
```

for protocols using the common Ollama worker.

---

## OCC wasted tokens

For a stale conflict:

```text
wastedTokens > 0
```

because the first Worker A LLM transaction is discarded.

---

## Dependency OCC

### Non-disruptive

Expected approximately:

```text
semanticPrediction = non_disruptive
wastedTokens = 0
nodesReexecuted = 0
```

### Disruptive

Expected approximately:

```text
semanticPrediction = disruptive
wastedTokens > 0
```

but ideally:

```text
Dependency-OCC wastedTokens
<
Full OCC wastedTokens
```

because A's unaffected preparation is preserved.

---

# 22. Do Not Run the Final Research Experiment Yet

Do not increase repetitions to 10, 20, or more until the corrected 16-run smoke benchmark passes.

The current order must be:

```text
fix MCP result extraction
        |
        v
test one raw MCP call
        |
        v
test MCP tools
        |
        v
run 16-run smoke benchmark
        |
        v
inspect CSVs
        |
        v
only then increase repetitions
```

---

# 23. Codex Implementation Rules

Follow these rules while making the repair.

1. Inspect existing code before editing.
2. Reuse working code.
3. Do not rewrite the architecture.
4. Do not bypass MCP for agent/shared-state access.
5. Keep MongoDB as the only persistence backend.
6. Keep async PyMongo API.
7. Keep version updates atomic.
8. Keep trace headers for:
   - run ID
   - agent ID
   - node ID
9. Keep Ollama local.
10. Keep `temperature=0` for benchmark model calls.
11. Keep the current two smoke-test scenarios.
12. Do not increase benchmark repetitions.
13. Do not fake or estimate token counts.
14. Do not hide exceptions.
15. Do not silently treat `None` MCP results as success.
16. Do not delete existing provenance/conflict collections.
17. Preserve Phase 1–5 behavior.
18. Use exact final-state checking for correctness.

---

# 24. Commands Codex Should Run

Assume the repository root is:

```text
D:\Research\MAS-research\dependency-aware-mcp
```

Run relevant tests from the repository root.

Recommended sequence:

```powershell
uv run python -m scripts.test_config
```

```powershell
uv run python -m scripts.test_ollama_tools
```

```powershell
uv run python -m scripts.seed_resource
```

Start MCP separately:

```powershell
uv run python -m app.mcp_server.server
```

Then:

```powershell
uv run python -m scripts.test_mcp_result_format
```

Then:

```powershell
uv run python -m scripts.test_mcp
```

Then:

```powershell
uv run python -m scripts.run_phase6_benchmark
```

Then:

```powershell
uv run python -m scripts.summarize_phase6
```

If an existing test command differs because of the current repository structure, use the actual module path discovered in the repo.

---

# 25. Completion Criteria

The repair is complete only when all of the following are true:

```text
[ ] MCP result extractor works
[ ] raw MCP read returns usable dictionary
[ ] no repeated "Unexpected MCP result: None"
[ ] no repeated "Unexpected MCP tool result: None"
[ ] read_shared_resource works
[ ] write_shared_resource works
[ ] baseline MCP tools work
[ ] Phase 6 runs all 16 smoke-test executions
[ ] all runs produce a final resource or a real protocol error
[ ] baseline scenarios use the actual BenchmarkScenario
[ ] correctness is compared to scenario.expected_final
[ ] token values are not all zero
[ ] full OCC records conflicts/retries
[ ] full OCC records wasted tokens on restart
[ ] Dependency OCC records semantic prediction
[ ] Dependency OCC benign case uses non-disruptive handling
[ ] Dependency OCC disruptive case uses selective recovery
[ ] node metrics distinguish affected vs reexecuted
[ ] benchmark_results.csv is generated
[ ] benchmark_summary.csv is generated
[ ] benchmark_scenario_summary.csv is generated
```

---

# 26. Required Codex Final Report

After making changes, Codex should report:

## Files changed

For each file:

```text
path
what changed
why
```

## Tests run

For each command:

```text
command
pass/fail
important output
```

## MCP result format

Show which field actually contained the tool result on the installed environment:

```text
data
structured_content
or content
```

## Phase 6 status

Report:

```text
number of benchmark runs attempted
number completed
number failed
```

## Smoke benchmark sanity checks

Report:

```text
2PL disruptive final state
OCC disruptive final state
Dependency OCC disruptive final state
whether token counts are non-zero
whether OCC wastedTokens > 0
whether semantic predictions are populated
```

## Remaining issues

If anything still fails, stop and report the exact remaining error instead of masking it.

---

