import asyncio

from app.evaluation.worker import (
    BenchmarkWorker,
)


async def main() -> None:

    worker = BenchmarkWorker("worker_a")

    preparation, prep_usage = await worker.prepare(
        task=("Allocate exactly 30 units " "from inventory.")
    )

    print("\nPREPARATION")

    print(preparation.model_dump_json(indent=2))

    print("\nPREPARATION TOKENS")

    print(prep_usage)

    decision, decision_usage = await worker.decide(
        task=("Allocate exactly 30 units " "from inventory."),
        preparation=preparation,
        current_state={
            "quantity": 60,
            "price": 20,
            "description": "Test Product",
        },
    )

    print("\nDECISION")

    print(decision.model_dump_json(indent=2))

    print("\nDECISION TOKENS")

    print(decision_usage)


if __name__ == "__main__":
    asyncio.run(main())
