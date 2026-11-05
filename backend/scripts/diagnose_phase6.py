import asyncio
from pprint import pprint

from app.evaluation.scenarios import SCENARIOS
from app.storage.mongodb import (
    benchmark_results,
    benchmark_runs,
    close_database,
)

SCENARIO_MAP = {scenario.scenario_id: scenario for scenario in SCENARIOS}


async def main() -> None:

    # =====================================================
    # FIND LATEST COMPLETED BENCHMARK
    # =====================================================

    latest_benchmark = await benchmark_runs.find_one(
        {"status": "completed"},
        sort=[("completedAt", -1)],
    )

    if latest_benchmark is None:

        print("No completed benchmark found.")

        await close_database()

        return

    benchmark_id = latest_benchmark["benchmarkId"]

    print("\n================================")
    print("PHASE 6 DIAGNOSTIC")
    print("================================")

    print(
        "Benchmark ID:",
        benchmark_id,
    )

    print(
        "Repetitions:",
        latest_benchmark.get("repetitions"),
    )

    # =====================================================
    # LOAD RESULTS
    # =====================================================

    results = await (
        benchmark_results.find(
            {"benchmarkId": benchmark_id},
            {"_id": 0},
        )
        .sort(
            [
                (
                    "scenarioId",
                    1,
                ),
                (
                    "protocol",
                    1,
                ),
            ]
        )
        .to_list(length=None)
    )

    if not results:

        print("No benchmark results found.")

        await close_database()

        return

    # =====================================================
    # PRINT EVERY SCENARIO
    # =====================================================

    for scenario in SCENARIOS:

        scenario_id = scenario.scenario_id

        print("\n\n" "================================")

        print(
            "SCENARIO:",
            scenario_id,
        )

        print(
            "TYPE:",
            scenario.semantic_ground_truth,
        )

        print("EXPECTED:")

        pprint(scenario.expected_final)

        print("================================")

        scenario_results = [
            result for result in results if result.get("scenarioId") == scenario_id
        ]

        for result in scenario_results:

            print("\n--------------------------------")

            print(
                "PROTOCOL:",
                result.get("protocol"),
            )

            print(
                "Correct:",
                result.get("correct"),
            )

            print("Final value:")

            pprint(result.get("finalValue"))

            print(
                "Final version:",
                result.get("finalVersion"),
            )

            print(
                "Conflicts:",
                result.get("conflicts"),
            )

            print(
                "Retries:",
                result.get("retries"),
            )

            print(
                "Semantic prediction:",
                result.get("semanticPrediction"),
            )

            print(
                "Semantic ground truth:",
                result.get("semanticGroundTruth"),
            )

            print(
                "Nodes reexecuted:",
                result.get("nodesReexecuted"),
            )

            print(
                "Nodes preserved:",
                result.get("nodesPreserved"),
            )

            print(
                "Total tokens:",
                result.get("totalTokens"),
            )

            print(
                "Wasted tokens:",
                result.get("wastedTokens"),
            )

            error = result.get("error")

            if error:

                print(
                    "ERROR:",
                    error,
                )

    # =====================================================
    # FAILED RUNS ONLY
    # =====================================================

    failed = [
        result
        for result in results
        if not result.get(
            "correct",
            False,
        )
    ]

    print("\n\n================================")
    print("FAILED RUNS")
    print("================================")

    print(
        "Failed:",
        len(failed),
        "/",
        len(results),
    )

    for result in failed:

        scenario_id = result.get("scenarioId")

        scenario = SCENARIO_MAP.get(scenario_id)

        print("\n--------------------------------")

        print(
            "Scenario:",
            scenario_id,
        )

        print(
            "Protocol:",
            result.get("protocol"),
        )

        if scenario:

            print("Expected:")

            pprint(scenario.expected_final)

        print("Actual:")

        pprint(result.get("finalValue"))

        print(
            "Conflict:",
            result.get("conflicts"),
        )

        print(
            "Semantic prediction:",
            result.get("semanticPrediction"),
        )

        print(
            "Error:",
            result.get("error"),
        )

    await close_database()


if __name__ == "__main__":

    asyncio.run(main())
