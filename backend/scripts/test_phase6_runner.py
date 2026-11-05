"""Isolated orchestration checks; run with python -m unittest scripts.test_phase6_runner."""

import io
import unittest
from collections import Counter
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.evaluation import runner
from app.evaluation.heldout_scenarios import HELDOUT_SCENARIOS
from app.evaluation.scenarios import SCENARIOS
from scripts.run_phase6_benchmark import select_scenarios


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def test_scenario_selection(self):
        self.assertIs(select_scenarios("validation")[0], SCENARIOS)
        self.assertEqual(select_scenarios("validation")[1], 20261102)
        self.assertIs(select_scenarios("heldout")[0], HELDOUT_SCENARIOS)
        self.assertEqual(select_scenarios("heldout")[1], 20261103)
        with self.assertRaises(ValueError):
            select_scenarios("unknown")

    async def exercise(self, repetitions, scenarios=HELDOUT_SCENARIOS):
        saved = []
        output = io.StringIO()
        repository = SimpleNamespace(
            start_benchmark=AsyncMock(), complete_benchmark=AsyncMock()
        )

        async def run_protocol(*, protocol="dependency_occ", **kwargs):
            return SimpleNamespace(
                **kwargs, protocol=protocol, correct=True, total_tokens=0,
                wasted_tokens=0, elapsed_ms=0.0, error=None,
            )

        async def save(result):
            saved.append(result)

        async def complete(**kwargs):
            self.assertEqual(len(saved), len(scenarios) * 4 * repetitions)

        repository.complete_benchmark.side_effect = complete
        with (
            patch.object(runner, "benchmark_repository", repository),
            patch.object(runner, "run_baseline", side_effect=run_protocol),
            patch.object(runner, "run_dependency_occ", side_effect=run_protocol),
            patch.object(runner, "save_result", side_effect=save),
            redirect_stdout(output),
        ):
            if isinstance(scenarios, DroppedScenarioList):
                with self.assertRaisesRegex(
                    RuntimeError, "Benchmark ended early: 36/40 runs completed."
                ):
                    await runner.run_benchmark(
                        repetitions=repetitions, scenarios=scenarios,
                        scenario_set="heldout", benchmark_seed=20261103,
                    )
                repository.complete_benchmark.assert_not_awaited()
                self.assertNotIn("BENCHMARK FINISHED", output.getvalue())
                return
            benchmark_id = await runner.run_benchmark(
                repetitions=repetitions, scenarios=scenarios,
                scenario_set="heldout", benchmark_seed=20261103,
            )

        expected = Counter(
            (repetition, scenario.scenario_id, protocol)
            for repetition in range(1, repetitions + 1)
            for scenario in scenarios
            for protocol in runner.PROTOCOLS
        )
        self.assertEqual(Counter(
            (r.repetition, r.scenario.scenario_id, r.protocol) for r in saved
        ), expected)
        repository.complete_benchmark.assert_awaited_once_with(benchmark_id=benchmark_id)
        metadata = repository.start_benchmark.call_args.kwargs
        self.assertEqual(metadata["benchmark_seed"], 20261103)
        self.assertEqual(metadata["scenario_set"], "heldout")
        text = output.getvalue()
        self.assertIn("Scenario set: heldout", text)
        self.assertIn("Benchmark seed: 20261103", text)
        self.assertNotIn("20261102", text)
        total = len(expected)
        self.assertIn(f"[{total}/{total}]", text)
        self.assertIn(f"Runs completed: {total}", text)
        self.assertIn(f"Expected runs: {total}", text)
        if repetitions == 2:
            self.assertLess(text.index("[40/80]"), text.index("[41/80]"))
            self.assertLess(text.index("[80/80]"), text.index("BENCHMARK FINISHED"))

    async def test_one_repetition(self):
        await self.exercise(1)

    async def test_two_repetitions(self):
        await self.exercise(2)

    async def test_ten_repetitions(self):
        await self.exercise(10)

    async def test_incomplete_benchmark_cannot_complete(self):
        await self.exercise(1, DroppedScenarioList(HELDOUT_SCENARIOS))


class DroppedScenarioList(list):
    def copy(self):
        return list(self[:-1])


if __name__ == "__main__":
    unittest.main()
