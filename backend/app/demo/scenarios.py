"""Controlled demo inputs, separate from evaluation scenarios."""

from copy import deepcopy

INITIAL_VALUE = {"quantity": 100, "price": 20, "description": "Test Product"}
SCENARIOS = [
    {
        "id": "non_disruptive", "name": "Price vs. quantity",
        "description": "An independent price change survives an inventory update.",
        "workerATask": "Set price to exactly 25. This decision is independent of quantity.",
        "workerBTask": "Set quantity to exactly 60.",
    },
    {
        "id": "disruptive", "name": "Inventory allocation",
        "description": "An allocation must be recalculated from current inventory.",
        "workerATask": "Allocate exactly 30 units from CURRENT quantity.",
        "workerBTask": "Set quantity to exactly 60.",
    },
]


def graph_input(demo_id: str, scenario_id: str) -> dict:
    scenario = next(item for item in SCENARIOS if item["id"] == scenario_id)
    initial = deepcopy(INITIAL_VALUE)
    stale = {**initial, "price": 25} if scenario_id == "non_disruptive" else {
        **initial, "quantity": initial["quantity"] - 30,
    }
    return {
        "run_id": demo_id, "resource_key": f"demo/{demo_id}/product_1",
        "scenario_name": scenario["name"], "initial_version": 1,
        "initial_value": initial, "b_write_value": {**initial, "quantity": 60},
        "a_stale_write_value": stale, "a_task_purpose": scenario["workerATask"],
    }
