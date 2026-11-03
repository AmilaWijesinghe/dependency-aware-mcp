import asyncio

from app.agents.auditor import SemanticAuditor


async def main() -> None:

    auditor = SemanticAuditor()

    decision = await auditor.classify(
        worker_purpose=(
            "Change only the product price from 20 to 25. "
            "This price decision does not depend on quantity."
        ),
        old_state={
            "quantity": 100,
            "price": 20,
            "description": "Test Product",
        },
        current_state={
            "quantity": 60,
            "price": 20,
            "description": "Test Product",
        },
        attempted_state={
            "quantity": 100,
            "price": 25,
            "description": "Test Product",
        },
        changed_fields={
            "quantity": {
                "old": 100,
                "new": 60,
            }
        },
        intended_changes={
            "price": {
                "old": 20,
                "new": 25,
            }
        },
    )

    print("\n==============================")
    print("SEMANTIC AUDITOR RESULT")
    print("==============================")

    print(decision.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
