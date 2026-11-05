from app.evaluation.heldout_scenarios import (
    HELDOUT_SCENARIOS,
)

EXPECTED_FIELDS = {
    "quantity",
    "price",
    "description",
}


def main() -> None:

    print("\n================================")
    print("HELD-OUT SCENARIO VALIDATION")
    print("================================")

    assert len(HELDOUT_SCENARIOS) == 10, (
        "Held-out set must contain " "exactly 10 scenarios."
    )

    ids = [scenario.scenario_id for scenario in HELDOUT_SCENARIOS]

    assert len(ids) == len(set(ids)), "Scenario IDs must be unique."

    non_disruptive = [
        scenario
        for scenario in HELDOUT_SCENARIOS
        if (scenario.semantic_ground_truth == "non_disruptive")
    ]

    disruptive = [
        scenario
        for scenario in HELDOUT_SCENARIOS
        if (scenario.semantic_ground_truth == "disruptive")
    ]

    assert len(non_disruptive) == 5

    assert len(disruptive) == 5

    for scenario in HELDOUT_SCENARIOS:

        print(
            "\nChecking:",
            scenario.scenario_id,
        )

        assert set(scenario.initial_value.keys()) == EXPECTED_FIELDS

        assert set(scenario.expected_final.keys()) == EXPECTED_FIELDS

        assert scenario.worker_a_operation.field in EXPECTED_FIELDS

        assert scenario.worker_b_operation.field in EXPECTED_FIELDS

        assert scenario.worker_a_task

        assert scenario.worker_b_task

        print(
            "  type:",
            scenario.semantic_ground_truth,
        )

        print(
            "  initial:",
            scenario.initial_value,
        )

        print(
            "  expected:",
            scenario.expected_final,
        )

    print("\n================================")
    print("HELD-OUT SET VALID")
    print("================================")

    print(
        "Scenarios:",
        len(HELDOUT_SCENARIOS),
    )

    print(
        "Non-disruptive:",
        len(non_disruptive),
    )

    print(
        "Disruptive:",
        len(disruptive),
    )


if __name__ == "__main__":
    main()
