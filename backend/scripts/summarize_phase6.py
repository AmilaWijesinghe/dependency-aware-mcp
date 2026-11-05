import asyncio
from pathlib import Path

import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)

from app.storage.mongodb import (
    benchmark_results,
    benchmark_runs,
    close_database,
)


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "results"


async def main() -> None:

    # =====================================================
    # 1. FIND THE LATEST COMPLETED BENCHMARK
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
    print("LATEST COMPLETED BENCHMARK")
    print("================================")

    print(
        "Benchmark ID:",
        benchmark_id,
    )

    print(
        "Model:",
        latest_benchmark.get("model"),
    )

    print(
        "Scenario set:",
        latest_benchmark.get("scenarioSet"),
    )

    print(
        "Repetitions:",
        latest_benchmark.get("repetitions"),
    )

    print(
        "Benchmark seed:",
        latest_benchmark.get("benchmarkSeed"),
    )

    print(
        "Started at:",
        latest_benchmark.get("startedAt"),
    )

    print(
        "Completed at:",
        latest_benchmark.get("completedAt"),
    )

    # =====================================================
    # 2. LOAD ONLY THE LATEST BENCHMARK RESULTS
    # =====================================================

    documents = await benchmark_results.find(
        {"benchmarkId": benchmark_id},
        {"_id": 0},
    ).to_list(length=None)

    if not documents:

        print("No benchmark results found.")

        await close_database()

        return

    df = pd.DataFrame(documents)

    print(
        "\nRuns loaded:",
        len(df),
    )

    # =====================================================
    # 3. NORMALIZE NUMERIC COLUMNS
    # =====================================================

    numeric_columns = [
        "elapsedMs",
        "inputTokens",
        "outputTokens",
        "totalTokens",
        "wastedTokens",
        "conflicts",
        "retries",
        "lockWaitMs",
        "nodesReexecuted",
        "nodesPreserved",
    ]

    for column in numeric_columns:

        if column in df.columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            ).fillna(0)

    if "correct" in df.columns:

        df["correct"] = df["correct"].fillna(False).astype(bool)

    # =====================================================
    # 4. ERROR SUMMARY
    # =====================================================

    if "error" in df.columns:

        error_df = df[df["error"].notna() & (df["error"].astype(str).str.strip() != "")]

    else:

        error_df = pd.DataFrame()

    print("\n================================")
    print("ERROR SUMMARY")
    print("================================")

    print(
        "Total runs:",
        len(df),
    )

    print(
        "Failed runs:",
        len(error_df),
    )

    print(
        "Completed without recorded error:",
        len(df) - len(error_df),
    )

    if not error_df.empty:

        print("\nErrors:")

        print(
            error_df[
                [
                    "protocol",
                    "scenarioId",
                    "repetition",
                    "error",
                ]
            ].to_string(index=False)
        )

    # =====================================================
    # 5. OVERALL PROTOCOL SUMMARY
    # =====================================================

    print("\n================================")
    print("PROTOCOL SUMMARY")
    print("================================")

    protocol_summary = (
        df.groupby("protocol")
        .agg(
            runs=(
                "correct",
                "count",
            ),
            successful_runs=(
                "correct",
                "sum",
            ),
            success_rate=(
                "correct",
                "mean",
            ),
            mean_latency_ms=(
                "elapsedMs",
                "mean",
            ),
            median_latency_ms=(
                "elapsedMs",
                "median",
            ),
            std_latency_ms=(
                "elapsedMs",
                "std",
            ),
            mean_input_tokens=(
                "inputTokens",
                "mean",
            ),
            mean_output_tokens=(
                "outputTokens",
                "mean",
            ),
            mean_tokens=(
                "totalTokens",
                "mean",
            ),
            median_tokens=(
                "totalTokens",
                "median",
            ),
            std_tokens=(
                "totalTokens",
                "std",
            ),
            mean_wasted_tokens=(
                "wastedTokens",
                "mean",
            ),
            median_wasted_tokens=(
                "wastedTokens",
                "median",
            ),
            mean_conflicts=(
                "conflicts",
                "mean",
            ),
            mean_retries=(
                "retries",
                "mean",
            ),
            mean_lock_wait_ms=(
                "lockWaitMs",
                "mean",
            ),
            mean_nodes_reexecuted=(
                "nodesReexecuted",
                "mean",
            ),
            mean_nodes_preserved=(
                "nodesPreserved",
                "mean",
            ),
        )
        .reset_index()
    )

    protocol_summary["success_rate_percent"] = protocol_summary["success_rate"] * 100

    print(protocol_summary.to_string(index=False))

    # =====================================================
    # 6. PER-SCENARIO SUMMARY
    # =====================================================

    print("\n================================")
    print("SCENARIO SUMMARY")
    print("================================")

    scenario_summary = (
        df.groupby(
            [
                "scenarioId",
                "semanticGroundTruth",
                "protocol",
            ],
            dropna=False,
        )
        .agg(
            runs=(
                "correct",
                "count",
            ),
            successful_runs=(
                "correct",
                "sum",
            ),
            success_rate=(
                "correct",
                "mean",
            ),
            mean_latency_ms=(
                "elapsedMs",
                "mean",
            ),
            median_latency_ms=(
                "elapsedMs",
                "median",
            ),
            std_latency_ms=(
                "elapsedMs",
                "std",
            ),
            mean_tokens=(
                "totalTokens",
                "mean",
            ),
            mean_wasted_tokens=(
                "wastedTokens",
                "mean",
            ),
            mean_conflicts=(
                "conflicts",
                "mean",
            ),
            mean_retries=(
                "retries",
                "mean",
            ),
            mean_lock_wait_ms=(
                "lockWaitMs",
                "mean",
            ),
            mean_nodes_reexecuted=(
                "nodesReexecuted",
                "mean",
            ),
            mean_nodes_preserved=(
                "nodesPreserved",
                "mean",
            ),
        )
        .reset_index()
    )

    scenario_summary["success_rate_percent"] = scenario_summary["success_rate"] * 100

    print(scenario_summary.to_string(index=False))

    # =====================================================
    # 7. SEMANTIC CONFLICT CLASS SUMMARY
    #
    # Compare disruptive vs non-disruptive scenarios.
    # =====================================================

    print("\n================================")
    print("SEMANTIC CLASS SUMMARY")
    print("================================")

    semantic_summary = (
        df.groupby(
            [
                "semanticGroundTruth",
                "protocol",
            ],
            dropna=False,
        )
        .agg(
            runs=(
                "correct",
                "count",
            ),
            successful_runs=(
                "correct",
                "sum",
            ),
            success_rate=(
                "correct",
                "mean",
            ),
            mean_latency_ms=(
                "elapsedMs",
                "mean",
            ),
            median_latency_ms=(
                "elapsedMs",
                "median",
            ),
            std_latency_ms=(
                "elapsedMs",
                "std",
            ),
            mean_tokens=(
                "totalTokens",
                "mean",
            ),
            mean_wasted_tokens=(
                "wastedTokens",
                "mean",
            ),
            mean_conflicts=(
                "conflicts",
                "mean",
            ),
            mean_retries=(
                "retries",
                "mean",
            ),
            mean_lock_wait_ms=(
                "lockWaitMs",
                "mean",
            ),
            mean_nodes_reexecuted=(
                "nodesReexecuted",
                "mean",
            ),
            mean_nodes_preserved=(
                "nodesPreserved",
                "mean",
            ),
        )
        .reset_index()
    )

    semantic_summary["success_rate_percent"] = semantic_summary["success_rate"] * 100

    print(semantic_summary.to_string(index=False))

    # =====================================================
    # 8. SEMANTIC AUDITOR EVALUATION
    # =====================================================

    auditor_df = df[
        (df["protocol"] == "dependency_occ")
        & (df["semanticPrediction"].notna())
        & (df["semanticGroundTruth"].notna())
    ].copy()

    print("\n================================")
    print("SEMANTIC AUDITOR")
    print("================================")

    if auditor_df.empty:

        print("No semantic auditor classifications found.")

        auditor_metrics = pd.DataFrame(
            [
                {
                    "classifications": 0,
                    "accuracy": None,
                    "precision": None,
                    "recall": None,
                    "f1": None,
                }
            ]
        )

    else:

        y_true = auditor_df["semanticGroundTruth"]

        y_pred = auditor_df["semanticPrediction"]

        accuracy = accuracy_score(
            y_true,
            y_pred,
        )

        precision = precision_score(
            y_true,
            y_pred,
            pos_label="disruptive",
            zero_division=0,
        )

        recall = recall_score(
            y_true,
            y_pred,
            pos_label="disruptive",
            zero_division=0,
        )

        f1 = f1_score(
            y_true,
            y_pred,
            pos_label="disruptive",
            zero_division=0,
        )

        print(
            "Classifications:",
            len(auditor_df),
        )

        print(f"Accuracy:  " f"{accuracy:.4f}")

        print(f"Precision: " f"{precision:.4f}")

        print(f"Recall:    " f"{recall:.4f}")

        print(f"F1:        " f"{f1:.4f}")

        # ---------------------------------------------
        # Classification counts
        # ---------------------------------------------

        classification_table = pd.crosstab(
            auditor_df["semanticGroundTruth"],
            auditor_df["semanticPrediction"],
            rownames=["actual"],
            colnames=["predicted"],
            dropna=False,
        )

        print("\nClassification table:")

        print(classification_table.to_string())

        auditor_metrics = pd.DataFrame(
            [
                {
                    "classifications": len(auditor_df),
                    "accuracy": accuracy,
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                }
            ]
        )

    # =====================================================
    # 9. OCC VS DEPENDENCY-OCC
    #
    # This is the main research comparison.
    # =====================================================

    print("\n================================")
    print("FULL OCC VS DEPENDENCY-OCC")
    print("================================")

    occ_rows = protocol_summary[protocol_summary["protocol"] == "occ"]

    dependency_rows = protocol_summary[protocol_summary["protocol"] == "dependency_occ"]

    comparison_rows = []

    if not occ_rows.empty and not dependency_rows.empty:

        occ = occ_rows.iloc[0]

        dependency = dependency_rows.iloc[0]

        occ_wasted = occ["mean_wasted_tokens"]

        dep_wasted = dependency["mean_wasted_tokens"]

        if occ_wasted > 0:

            wasted_reduction = (occ_wasted - dep_wasted) / occ_wasted * 100

        else:

            wasted_reduction = 0.0

        occ_latency = occ["mean_latency_ms"]

        dep_latency = dependency["mean_latency_ms"]

        if occ_latency > 0:

            latency_change = (dep_latency - occ_latency) / occ_latency * 100

        else:

            latency_change = 0.0

        occ_tokens = occ["mean_tokens"]

        dep_tokens = dependency["mean_tokens"]

        if occ_tokens > 0:

            token_change = (dep_tokens - occ_tokens) / occ_tokens * 100

        else:

            token_change = 0.0

        occ_reexecuted = occ["mean_nodes_reexecuted"]

        dep_reexecuted = dependency["mean_nodes_reexecuted"]

        occ_preserved = occ["mean_nodes_preserved"]

        dep_preserved = dependency["mean_nodes_preserved"]

        print(
            "Full OCC mean wasted tokens:",
            f"{occ_wasted:.2f}",
        )

        print(
            "Dependency-OCC mean wasted tokens:",
            f"{dep_wasted:.2f}",
        )

        print(
            "Wasted-token reduction:",
            f"{wasted_reduction:.2f}%",
        )

        print(
            "\nFull OCC mean latency:",
            f"{occ_latency:.2f} ms",
        )

        print(
            "Dependency-OCC mean latency:",
            f"{dep_latency:.2f} ms",
        )

        print(
            "Dependency-OCC latency change:",
            f"{latency_change:+.2f}%",
        )

        print(
            "\nFull OCC mean total tokens:",
            f"{occ_tokens:.2f}",
        )

        print(
            "Dependency-OCC mean total tokens:",
            f"{dep_tokens:.2f}",
        )

        print(
            "Dependency-OCC total-token change:",
            f"{token_change:+.2f}%",
        )

        print(
            "\nFull OCC mean nodes reexecuted:",
            f"{occ_reexecuted:.2f}",
        )

        print(
            "Dependency-OCC mean nodes reexecuted:",
            f"{dep_reexecuted:.2f}",
        )

        print(
            "Full OCC mean nodes preserved:",
            f"{occ_preserved:.2f}",
        )

        print(
            "Dependency-OCC mean nodes preserved:",
            f"{dep_preserved:.2f}",
        )

        comparison_rows.append(
            {
                "metric": "mean_wasted_tokens",
                "full_occ": occ_wasted,
                "dependency_occ": dep_wasted,
                "percent_change_dependency_vs_occ": -wasted_reduction,
            }
        )

        comparison_rows.append(
            {
                "metric": "mean_latency_ms",
                "full_occ": occ_latency,
                "dependency_occ": dep_latency,
                "percent_change_dependency_vs_occ": latency_change,
            }
        )

        comparison_rows.append(
            {
                "metric": "mean_total_tokens",
                "full_occ": occ_tokens,
                "dependency_occ": dep_tokens,
                "percent_change_dependency_vs_occ": token_change,
            }
        )

        comparison_rows.append(
            {
                "metric": "mean_nodes_reexecuted",
                "full_occ": occ_reexecuted,
                "dependency_occ": dep_reexecuted,
                "percent_change_dependency_vs_occ": None,
            }
        )

        comparison_rows.append(
            {
                "metric": "mean_nodes_preserved",
                "full_occ": occ_preserved,
                "dependency_occ": dep_preserved,
                "percent_change_dependency_vs_occ": None,
            }
        )

    else:

        print("OCC or Dependency-OCC results are missing.")

    occ_vs_dependency = pd.DataFrame(comparison_rows)

    # =====================================================
    # 10. OCC VS DEPENDENCY-OCC BY SEMANTIC CLASS
    # =====================================================

    print("\n================================")
    print("OCC VS DEPENDENCY-OCC BY " "SEMANTIC CLASS")
    print("================================")

    semantic_comparison_rows = []

    semantic_classes = [
        "non_disruptive",
        "disruptive",
    ]

    for semantic_class in semantic_classes:

        class_df = semantic_summary[
            semantic_summary["semanticGroundTruth"] == semantic_class
        ]

        occ_class = class_df[class_df["protocol"] == "occ"]

        dep_class = class_df[class_df["protocol"] == "dependency_occ"]

        if occ_class.empty or dep_class.empty:
            continue

        occ = occ_class.iloc[0]

        dep = dep_class.iloc[0]

        occ_wasted = occ["mean_wasted_tokens"]

        dep_wasted = dep["mean_wasted_tokens"]

        if occ_wasted > 0:

            wasted_reduction = (occ_wasted - dep_wasted) / occ_wasted * 100

        else:

            wasted_reduction = 0.0

        occ_latency = occ["mean_latency_ms"]

        dep_latency = dep["mean_latency_ms"]

        if occ_latency > 0:

            latency_change = (dep_latency - occ_latency) / occ_latency * 100

        else:

            latency_change = 0.0

        print(f"\n{semantic_class.upper()}")

        print(
            "OCC wasted tokens:",
            f"{occ_wasted:.2f}",
        )

        print(
            "Dependency-OCC wasted tokens:",
            f"{dep_wasted:.2f}",
        )

        print(
            "Wasted-token reduction:",
            f"{wasted_reduction:.2f}%",
        )

        print(
            "OCC latency:",
            f"{occ_latency:.2f} ms",
        )

        print(
            "Dependency-OCC latency:",
            f"{dep_latency:.2f} ms",
        )

        print(
            "Dependency-OCC latency change:",
            f"{latency_change:+.2f}%",
        )

        semantic_comparison_rows.append(
            {
                "semantic_class": semantic_class,
                "occ_mean_wasted_tokens": occ_wasted,
                "dependency_mean_wasted_tokens": dep_wasted,
                "wasted_token_reduction_percent": wasted_reduction,
                "occ_mean_latency_ms": occ_latency,
                "dependency_mean_latency_ms": dep_latency,
                "dependency_latency_change_percent": latency_change,
            }
        )

    semantic_comparison = pd.DataFrame(semantic_comparison_rows)

    # =====================================================
    # 11. EXPORT CSV FILES
    # =====================================================

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df.to_csv(
        OUTPUT_DIR / "benchmark_results.csv",
        index=False,
    )

    protocol_summary.to_csv(
        OUTPUT_DIR / "benchmark_summary.csv",
        index=False,
    )

    scenario_summary.to_csv(
        OUTPUT_DIR / "benchmark_scenario_summary.csv",
        index=False,
    )

    semantic_summary.to_csv(
        OUTPUT_DIR / "benchmark_semantic_summary.csv",
        index=False,
    )

    auditor_metrics.to_csv(
        OUTPUT_DIR / "benchmark_auditor_metrics.csv",
        index=False,
    )

    if not occ_vs_dependency.empty:

        occ_vs_dependency.to_csv(
            OUTPUT_DIR / "benchmark_occ_vs_dependency.csv",
            index=False,
        )

    if not semantic_comparison.empty:

        semantic_comparison.to_csv(
            OUTPUT_DIR / "benchmark_semantic_comparison.csv",
            index=False,
        )

    # =====================================================
    # 12. FINAL OUTPUT
    # =====================================================

    print("\n================================")
    print("FILES CREATED")
    print("================================")

    print("Output directory:", OUTPUT_DIR)

    print("benchmark_results.csv")

    print("benchmark_summary.csv")

    print("benchmark_scenario_summary.csv")

    print("benchmark_semantic_summary.csv")

    print("benchmark_auditor_metrics.csv")

    if not occ_vs_dependency.empty:

        print("benchmark_occ_vs_dependency.csv")

    if not semantic_comparison.empty:

        print("benchmark_semantic_comparison.csv")

    await close_database()


if __name__ == "__main__":
    asyncio.run(main())
