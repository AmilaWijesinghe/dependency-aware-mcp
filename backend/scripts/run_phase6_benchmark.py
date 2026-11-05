import argparse
import asyncio

from langchain_ollama import (
    ChatOllama,
)

from app.config import settings

from app.evaluation.heldout_scenarios import (
    HELDOUT_SCENARIOS,
)

from app.evaluation.runner import (
    PROTOCOLS,
    run_benchmark,
)

from app.evaluation.scenarios import (
    SCENARIOS,
)

from app.storage.mongodb import (
    close_database,
    ensure_indexes,
    ping_database,
)

VALIDATION_SEED = 20261102

HELDOUT_SEED = 20261103


async def warmup_model() -> None:

    print("\nWarming up Ollama...")

    model = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0,
    )

    response = await model.ainvoke("Reply with the word READY.")

    print(
        "Warmup:",
        response.content,
    )


def select_scenarios(
    scenario_set: str,
):

    if scenario_set == "validation":

        return (
            SCENARIOS,
            VALIDATION_SEED,
        )

    if scenario_set == "heldout":

        return (
            HELDOUT_SCENARIOS,
            HELDOUT_SEED,
        )

    raise ValueError(f"Unknown scenario set: " f"{scenario_set}")


async def main(
    *,
    repetitions: int,
    scenario_set: str,
) -> None:

    if repetitions < 1:

        raise ValueError("repetitions must be " "at least 1")

    (
        scenarios,
        benchmark_seed,
    ) = select_scenarios(scenario_set)

    await ping_database()

    print("MongoDB connected.")

    await ensure_indexes()

    await warmup_model()

    print("\n================================")

    print("BENCHMARK CONFIGURATION")

    print("================================")

    print(
        "Scenario set:",
        scenario_set,
    )

    print(
        "Scenarios:",
        len(scenarios),
    )

    print("Protocols:", len(PROTOCOLS))

    print(
        "Repetitions:",
        repetitions,
    )

    print(
        "Benchmark seed:",
        benchmark_seed,
    )

    print(
        "Expected runs:",
        (len(scenarios) * len(PROTOCOLS) * repetitions),
    )

    benchmark_id = await run_benchmark(
        repetitions=repetitions,
        scenarios=scenarios,
        scenario_set=scenario_set,
        benchmark_seed=benchmark_seed,
    )

    print("\nBenchmark completed.")

    print(
        "Benchmark ID:",
        benchmark_id,
    )

    print("\nGenerate summary with:")

    print("uv run python " "-m scripts.summarize_phase6")

    await close_database()


def parse_args():

    parser = argparse.ArgumentParser(description=("Run Phase 6 benchmark."))

    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--scenario-set",
        choices=[
            "validation",
            "heldout",
        ],
        default="validation",
        help=("Choose development validation " "or held-out final scenarios."),
    )

    return parser.parse_args()


if __name__ == "__main__":

    args = parse_args()

    asyncio.run(
        main(
            repetitions=args.repetitions,
            scenario_set=args.scenario_set,
        )
    )
