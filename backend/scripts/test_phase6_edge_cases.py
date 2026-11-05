"""Phase 6 schema regressions and live Ollama worker/auditor edge checks.

Run before the MCP-backed benchmark. These checks exercise model decisions
directly; they do not read or mutate the shared benchmark resource.
"""

import asyncio

from pydantic import ValidationError

from app.agents.auditor import SemanticAuditor
from app.concurrency.auditor_service import calculate_diff
from app.evaluation.schemas import WorkerDecision
from app.evaluation.worker import BenchmarkWorker


INITIAL = {"quantity": 100, "price": 20, "description": "Test Product"}


def check(condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


def check_schema() -> None:
    for payload in ({}, {"new_value": None}, {"new_value": {}},
                    {"new_value": INITIAL}):
        decision = WorkerDecision.model_validate({"action": "stop", **payload})
        check(decision.new_value is None, f"STOP not normalized: {decision}")

    for value in (None, {},
                  {"quantity": 100, "price": 20,
                   "product_description": "Premium Product"},
                  {**INITIAL, "product_description": "Premium Product"}):
        try:
            WorkerDecision(action="write", new_value=value)
        except ValidationError:
            continue
        raise AssertionError(f"Invalid write accepted: {value!r}")
    check(WorkerDecision(action="write", new_value=INITIAL).new_value == INITIAL,
          "Valid complete write rejected")
    print("schema: STOP normalization and exact write contract passed", flush=True)


async def main() -> None:
    check_schema()
    worker = BenchmarkWorker("phase6_edge_worker")
    cases = [
        ("allocation impossible", {**INITIAL, "quantity": 40},
         "Allocate exactly 50 units from CURRENT quantity by subtracting 50. "
         "If fewer than 50 are available, stop without writing. "
         "Preserve price and description.", None),
        ("threshold condition", {**INITIAL, "quantity": 60},
         "Set price to exactly 18 only if CURRENT quantity is at least 80. "
         "Otherwise stop without writing. Preserve quantity and description.", None),
        ("description condition", {**INITIAL, "description": "Discontinued Product"},
         "Set price to exactly 25 only if CURRENT description is exactly "
         "'Test Product'. Otherwise stop without writing. "
         "Preserve quantity and description.", None),
        ("description output", INITIAL.copy(),
         "Set the product description to exactly 'Premium Product'. "
         "Preserve quantity and price.", {**INITIAL, "description": "Premium Product"}),
        ("current-price arithmetic", {**INITIAL, "price": 12},
         "Reduce the CURRENT product price by exactly 5. Calculate from the "
         "current price. Preserve quantity and description.", {**INITIAL, "price": 7}),
    ]
    for label, state, task, expected in cases:
        preparation, _ = await worker.prepare(task=task)
        decision, _ = await worker.decide(
            task=task, preparation=preparation, current_state=state,
        )
        check(decision.action == ("stop" if expected is None else "write")
              and decision.new_value == expected,
              f"{label}: unexpected decision {decision.model_dump()!r}")
        print(f"{label} -> {decision.action}; new_value={decision.new_value!r}", flush=True)
        if expected is not None:
            check(set(decision.new_value) == set(INITIAL), "Resource keys changed")
            print(f"resource keys: {sorted(decision.new_value)}", flush=True)

    current = {**INITIAL, "price": 12}
    attempted = {**INITIAL, "price": 15}
    audit = await SemanticAuditor().classify(
        worker_purpose="Reduce the CURRENT product price by exactly 5. "
                       "Preserve quantity and description.",
        old_state=INITIAL, current_state=current, attempted_state=attempted,
        changed_fields=calculate_diff(INITIAL, current),
        intended_changes=calculate_diff(INITIAL, attempted),
    )
    print(f"Auditor -> {audit.semantic_result}; reason={audit.reason}", flush=True)
    check(audit.semantic_result == "disruptive", f"Arithmetic audit failed: {audit}")
    print("ALL PHASE 6 EDGE TESTS PASSED", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
