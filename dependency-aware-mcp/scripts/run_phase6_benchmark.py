import argparse
import asyncio

from langchain_ollama import ChatOllama

from app.config import settings
from app.evaluation.runner import (
    run_benchmark,
)
from app.storage.mongodb import (
    close_database,
    ensure_indexes,
    ping_database,
)


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


async def main(
    repetitions: int,
) -> None:

    if repetitions < 1:

        raise ValueError("repetitions must be at least 1")

    await ping_database()

    print("MongoDB connected.")

    await ensure_indexes()

    await warmup_model()

    print(
        "\nRequested repetitions:",
        repetitions,
    )

    benchmark_id = await run_benchmark(repetitions=repetitions)

    print("\nBenchmark completed.")

    print(
        "Benchmark ID:",
        benchmark_id,
    )

    print("\nGenerate summary with:")

    print("uv run python " "-m scripts.summarize_phase6")

    await close_database()


def parse_args():

    parser = argparse.ArgumentParser(
        description=("Run the Phase 6 concurrency benchmark.")
    )

    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help=("Number of repetitions for every " "scenario/protocol combination."),
    )

    return parser.parse_args()


if __name__ == "__main__":

    args = parse_args()

    asyncio.run(main(repetitions=(args.repetitions)))
