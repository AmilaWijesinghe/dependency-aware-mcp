# Phase 6 MCP result repair validation

This report covers smoke validation with two scenarios, four protocols, and two repetitions. These are not final research results.

## Repair

The live MCP server returned `data=None` and `structured_content=None`. The dictionary was JSON in a `content` TextContent block. The baseline and evaluation runner each had a parser that required `result.data` to be a dictionary, causing the reported failures.

All raw dictionary-returning MCP calls now use `extract_tool_data`. It prefers `data`, then `structured_content`, then JSON text. It handles a sole `result` wrapper in structured/text output, rejects MCP error responses, preserves protocol conflict statuses, and raises diagnostic errors for missing or ambiguous dictionaries. The earlier `tool_result_dict` name remains a compatibility alias to the same function.

The first live batch exposed a separate 2PL scheduling race: its 10 ms delay could let A acquire the lock first. Provenance for run `ee969744-4418-47b1-8045-6c7efa1e8ccd` showed A reading quantity 100 and writing 70, followed by B reading 70 and writing 60. This is a valid serialization, but differs from the B-before-A workload required by the benchmark. An event now signals B's actual lock acquisition before A begins contending. On failure, pending transaction tasks are cancelled before the original error propagates.

## Files changed by this repair

Existing unrelated working-tree changes were preserved.

| File | Change and reason |
| --- | --- |
| `app/mcp_client/traced_tools.py` | Added the shared extractor; retained the single traced client/tools definitions and all three provenance headers. |
| `app/mcp_client/results.py` | Replaced its separate parser with a compatibility alias, leaving one implementation. |
| `app/protocols/baselines.py` | Removed the data-only parser; shared extraction also validates lock release and rejects unexpected acquisition statuses. Replaced the 2PL timing assumption with explicit B-first synchronization and failure cleanup. |
| `app/evaluation/runner.py` | Removed the duplicate data-only parser and used the shared extractor. |
| `app/concurrency/recovery_service.py` | Routed raw recovery writes through the shared extractor. |
| `app/graph/phase4.py` | Routed recovery reads, writes, and verification through the shared extractor. |
| `scripts/test_mcp_result_format.py` | Added the required live diagnostic, including all three raw fields and assertions on the extracted resource. |
| `scripts/test_mcp.py` | Added assertions for all seven expected tools and a successfully extracted resource read. |
| `tests/test_mcp_results.py` | Added extraction precedence, wrapper, mixed text, missing-result diagnostics, and compatibility-alias coverage. |
| `tests/test_protocol_baselines.py` | Updated stale signatures to current scenarios, isolated model calls in tests, covered both scenarios with real MCP responses, and added delayed-B scheduling coverage. |
| `benchmark_results.csv` | Regenerated from the latest completed smoke benchmark. |
| `benchmark_summary.csv` | Regenerated protocol aggregates from that same benchmark. |
| `benchmark_scenario_summary.csv` | Regenerated per-scenario aggregates from that same benchmark. |
| `PHASE6_MCP_RESULT_FIX_REPORT.md` | Recorded the repair, exact validation commands, results, and remaining limitation. |

No persistence, worker model, scenario, atomic version update, or benchmark repetition configuration was changed.

## Validation commands

`scripts/test_config.py` does not exist. The following configuration check succeeded without printing the MongoDB credential:

```powershell
uv run python -c "from app.config import settings; print('MongoDB URI configured:', bool(settings.mongodb_uri)); print('MongoDB database:', settings.mongodb_database); print('Ollama worker model:', settings.ollama_model); print('Ollama auditor model:', settings.ollama_auditor_model or settings.ollama_model); print('Ollama URL:', settings.ollama_base_url); print('MCP URL:', settings.mcp_url)"
```

It reported database `dependency_aware_mcp`, model `qwen2.5:14b`, Ollama `http://localhost:11434`, and MCP `http://127.0.0.1:8001/mcp`.

| Exact command | Result |
| --- | --- |
| `uv run python -m unittest discover -s tests -p test_mcp_results.py -v` | PASS: 9 tests in its final execution, including an actual in-process SDK server response. |
| `uv run python -m unittest discover -s tests -p test_protocol_baselines.py -v` | PASS: 4 tests in its final execution; both scenarios and delayed B lock connection covered. |
| `uv run python -m unittest discover -s tests -p test_research_trace.py -v` | PASS: 3 tests; adapter/raw-client headers, concurrent identities, and missing-header rejection. |
| `uv run python -m scripts.test_ollama_tools` | PASS: `response.tool_calls` contained `get_test_number`. |
| `uv run python -m scripts.seed_resource` | PASS: seeded quantity 100, price 20, description Test Product, version 1. |
| `uv run python -m app.mcp_server.server` | Started the local server on port 8001 for live validation. |
| `uv run python -m scripts.test_mcp_result_format` | PASS: recovered the expected dictionary from `content`; `data` and `structured_content` were both None. |
| `uv run python -m scripts.test_mcp` | PASS: all seven expected tools exposed; resource read and extraction succeeded. |
| `uv run python -u -m scripts.run_phase6_benchmark` | Executed twice with repetitions fixed at 2; details below. |
| `uv run python -m scripts.summarize_phase6` | PASS: loaded exactly 16 rows for the final batch and regenerated all three CSV files. |
| `uv run python -m pytest -q` | BLOCKED during collection by the pre-existing legacy import error below. |
| `git diff --check` | PASS; existing CRLF conversion warnings only. |

The initial sandboxed uv invocations failed to access the cache lock at `C:\Users\amila\AppData\Local\uv\cache\.lock`; they were rerun with the required escalation and succeeded.

## Smoke batches

First batch: `83b7fd0b-0178-463a-837e-b6c4e04c71df`.

- 16 attempted, 16 completed, zero runtime errors.
- 11 correct final states; four expected naive lost updates and one 2PL serialization-order mismatch.
- The mismatch was diagnosed from stored results and provenance before changing scheduling.

Final batch: `83b58ea5-7f94-4fd5-9f18-3c364bb181b5`.

- 16 attempted, 16 completed, zero runtime errors.
- All 12 runs using 2PL, full OCC, or dependency OCC produced the correct final state.
- All four naive runs completed but produced the expected incorrect state from a stale write.
- Across both batches: 32 attempted and completed, zero runtime errors. Only the latest 16 are included in the regenerated CSVs.

The disruptive final state was exactly `{'quantity': 30, 'price': 20, 'description': 'Test Product'}` for both repetitions of 2PL, full OCC, and dependency OCC. Naive ended at quantity 70. In the independent-fields scenario, the three concurrency-control protocols ended at quantity 60 and price 25; naive lost B's update and ended at quantity 100.

All 16 final-batch token counts were positive, ranging from 988 to 2258, using actual model usage metadata.

| Protocol/scenario | Wasted tokens per run | Conflicts | Retries | Nodes reexecuted | Nodes preserved |
| --- | ---: | ---: | ---: | ---: | ---: |
| Naive, either scenario | 0 | 0 | 0 | 0 | 0 |
| 2PL, either scenario | 0 | 0 | 0 | 0 | 0 |
| Full OCC, independent fields | 511 | 1 | 1 | 4 | 4 |
| Full OCC, disruptive inventory | 711 | 1 | 1 | 4 | 4 |
| Dependency OCC, independent fields | 0 | 1 | 0 | 0 | 7 |
| Dependency OCC, disruptive inventory | 442 | 1 | 0 | 3 | 5 |

Dependency OCC populated all four semantic predictions: two `non_disruptive` and two `disruptive`, matching ground truth. Its disruptive wasted tokens (442) were below full OCC's (711). Its benign path rebased without reexecuting reasoning; its disruptive path reexecuted three nodes and preserved preparation and B's work.

All CSV sanity assertions passed. They checked the exact benchmark ID and 16-row scenario/protocol/repetition coverage, absence of runtime errors, independently recomputed correctness from each stored final value, positive token usage, OCC conflict/retry/waste values, semantic labels, and selective recovery metrics. The exact command was:

```powershell
uv run python -c "import ast; import pandas as pd; from app.evaluation.scenarios import SCENARIOS; df=pd.read_csv('benchmark_results.csv'); expected={s.scenario_id: s.expected_final for s in SCENARIOS}; assert len(df)==16; assert set(df.benchmarkId)=={'83b58ea5-7f94-4fd5-9f18-3c364bb181b5'}; assert df.groupby(['scenarioId','protocol']).size().eq(2).all(); assert df.error.isna().all(); assert df.totalTokens.gt(0).all(); assert df[df.protocol.ne('naive')].correct.all(); assert all(row.correct == (ast.literal_eval(row.finalValue) == expected[row.scenarioId]) for row in df.itertuples()); occ=df[df.protocol.eq('occ')]; assert occ.conflicts.eq(1).all() and occ.retries.eq(1).all() and occ.wastedTokens.gt(0).all(); dep=df[df.protocol.eq('dependency_occ')]; assert dep.semanticPrediction.eq(dep.semanticGroundTruth).all(); benign=dep[dep.scenarioId.eq('benign_independent_fields')]; disruptive=dep[dep.scenarioId.eq('disruptive_inventory')]; assert benign.wastedTokens.eq(0).all() and benign.nodesReexecuted.eq(0).all(); assert disruptive.wastedTokens.gt(0).all() and disruptive.nodesReexecuted.eq(3).all(); assert disruptive.wastedTokens.max() < occ[occ.scenarioId.eq('disruptive_inventory')].wastedTokens.min(); assert df[df.protocol.isin(['naive','2pl'])].wastedTokens.eq(0).all(); print('CSV sanity checks: PASS'); print('Rows:',len(df),'Runtime errors:',df.error.notna().sum(),'Correct:',df.correct.sum()); print('Token range:',df.totalTokens.min(),df.totalTokens.max()); print(df[['repetition','scenarioId','protocol','correct','finalValue','totalTokens','wastedTokens','conflicts','retries','semanticPrediction','nodesReexecuted','nodesPreserved']].to_string(index=False))"
```

The local MCP server was kept running on port 8001 after validation.

## Remaining test-suite limitation

The full pytest suite fails before collecting tests:

```text
ImportError: cannot import name 'ConflictResult' from 'app.schemas.conflict'
```

The import originates in `tests/conftest.py`, through legacy `app.concurrency.provenance` and `app.concurrency.conflicts`. Those fixtures target the older SQLite implementation. They were not rebuilt or changed as part of the current MongoDB/MCP repair. The focused tests above run independently with unittest.
