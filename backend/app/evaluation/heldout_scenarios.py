from app.evaluation.schemas import (
    BenchmarkScenario,
    OperationSpec,
)

# =========================================================
# HELD-OUT FINAL EVALUATION SET
#
# IMPORTANT:
# Do not use these scenarios for prompt tuning.
# Do not modify Worker/Auditor prompts based on results
# from this file.
#
# 5 non-disruptive
# 5 disruptive
# =========================================================


HELDOUT_SCENARIOS = [
    # =====================================================
    # NON-DISRUPTIVE 1
    #
    # Fixed price update is independent of description.
    # =====================================================
    BenchmarkScenario(
        scenario_id=("ho_nd_fixed_price_vs_description"),
        name=("Held-out fixed price versus " "description update"),
        semantic_ground_truth=("non_disruptive"),
        initial_value={
            "quantity": 85,
            "price": 24,
            "description": "Everyday Item",
        },
        worker_a_task=(
            "Set the product price to exactly 27. "
            "This is a fixed target and does not "
            "depend on the product description or "
            "inventory quantity. Preserve all other "
            "fields."
        ),
        worker_b_task=(
            "Set the product description to exactly "
            "'Seasonal Label'. Preserve quantity "
            "and price."
        ),
        worker_a_operation=OperationSpec(
            operation="set",
            field="price",
            value=27,
        ),
        worker_b_operation=OperationSpec(
            operation="set",
            field="description",
            value="Seasonal Label",
        ),
        expected_final={
            "quantity": 85,
            "price": 27,
            "description": "Seasonal Label",
        },
    ),
    # =====================================================
    # NON-DISRUPTIVE 2
    #
    # Fixed quantity independent of price.
    # =====================================================
    BenchmarkScenario(
        scenario_id=("ho_nd_fixed_quantity_vs_price"),
        name=("Held-out fixed quantity versus " "price update"),
        semantic_ground_truth=("non_disruptive"),
        initial_value={
            "quantity": 140,
            "price": 16,
            "description": "Warehouse Item",
        },
        worker_a_task=(
            "Set inventory quantity to exactly 120. "
            "This is a fixed target and does not "
            "depend on the current product price. "
            "Preserve price and description."
        ),
        worker_b_task=(
            "Set the product price to exactly 19. " "Preserve quantity and description."
        ),
        worker_a_operation=OperationSpec(
            operation="set",
            field="quantity",
            value=120,
        ),
        worker_b_operation=OperationSpec(
            operation="set",
            field="price",
            value=19,
        ),
        expected_final={
            "quantity": 120,
            "price": 19,
            "description": "Warehouse Item",
        },
    ),
    # =====================================================
    # NON-DISRUPTIVE 3
    #
    # Fixed description independent of quantity.
    # =====================================================
    BenchmarkScenario(
        scenario_id=("ho_nd_description_vs_quantity"),
        name=("Held-out description versus " "quantity update"),
        semantic_ground_truth=("non_disruptive"),
        initial_value={
            "quantity": 65,
            "price": 32,
            "description": "Standard Box",
        },
        worker_a_task=(
            "Set the product description to exactly "
            "'Gift Packaging'. This decision is "
            "independent of inventory quantity. "
            "Preserve quantity and price."
        ),
        worker_b_task=(
            "Set inventory quantity to exactly 50. " "Preserve price and description."
        ),
        worker_a_operation=OperationSpec(
            operation="set",
            field="description",
            value="Gift Packaging",
        ),
        worker_b_operation=OperationSpec(
            operation="set",
            field="quantity",
            value=50,
        ),
        expected_final={
            "quantity": 50,
            "price": 32,
            "description": "Gift Packaging",
        },
    ),
    # =====================================================
    # NON-DISRUPTIVE 4
    #
    # Price independent of description.
    # =====================================================
    BenchmarkScenario(
        scenario_id=("ho_nd_price_vs_label_change"),
        name=("Held-out independent price and label"),
        semantic_ground_truth=("non_disruptive"),
        initial_value={
            "quantity": 30,
            "price": 45,
            "description": "Limited Item",
        },
        worker_a_task=(
            "Set the product price to exactly 42. "
            "This price is predetermined and does "
            "not depend on product description or "
            "quantity. Preserve all other fields."
        ),
        worker_b_task=(
            "Set the product description to exactly "
            "'New Label'. Preserve quantity and "
            "price."
        ),
        worker_a_operation=OperationSpec(
            operation="set",
            field="price",
            value=42,
        ),
        worker_b_operation=OperationSpec(
            operation="set",
            field="description",
            value="New Label",
        ),
        expected_final={
            "quantity": 30,
            "price": 42,
            "description": "New Label",
        },
    ),
    # =====================================================
    # NON-DISRUPTIVE 5
    #
    # Description independent of price.
    # =====================================================
    BenchmarkScenario(
        scenario_id=("ho_nd_description_vs_price"),
        name=("Held-out independent description " "and price"),
        semantic_ground_truth=("non_disruptive"),
        initial_value={
            "quantity": 200,
            "price": 11,
            "description": "Bulk Item",
        },
        worker_a_task=(
            "Set the product description to exactly "
            "'Bulk Promotion'. This description "
            "change is independent of the product "
            "price. Preserve quantity and price."
        ),
        worker_b_task=(
            "Set the product price to exactly 14. " "Preserve quantity and description."
        ),
        worker_a_operation=OperationSpec(
            operation="set",
            field="description",
            value="Bulk Promotion",
        ),
        worker_b_operation=OperationSpec(
            operation="set",
            field="price",
            value=14,
        ),
        expected_final={
            "quantity": 200,
            "price": 14,
            "description": "Bulk Promotion",
        },
    ),
    # =====================================================
    # DISRUPTIVE 1
    #
    # Arithmetic dependency on CURRENT quantity.
    # =====================================================
    BenchmarkScenario(
        scenario_id=("ho_d_allocate_12_after_quantity_change"),
        name=("Held-out current quantity arithmetic"),
        semantic_ground_truth=("disruptive"),
        initial_value={
            "quantity": 85,
            "price": 24,
            "description": "Everyday Item",
        },
        worker_a_task=(
            "Allocate exactly 12 units from the "
            "CURRENT inventory quantity. Subtract "
            "12 from the current quantity. If fewer "
            "than 12 units are available, stop. "
            "Preserve price and description."
        ),
        worker_b_task=(
            "Set inventory quantity to exactly 44. " "Preserve price and description."
        ),
        worker_a_operation=OperationSpec(
            operation="subtract",
            field="quantity",
            amount=12,
        ),
        worker_b_operation=OperationSpec(
            operation="set",
            field="quantity",
            value=44,
        ),
        # B => 44
        # fresh A => 44 - 12 = 32
        expected_final={
            "quantity": 32,
            "price": 24,
            "description": "Everyday Item",
        },
    ),
    # =====================================================
    # DISRUPTIVE 2
    #
    # Current price controls a description decision.
    # =====================================================
    BenchmarkScenario(
        scenario_id=("ho_d_price_threshold_controls_description"),
        name=("Held-out price threshold dependency"),
        semantic_ground_truth=("disruptive"),
        initial_value={
            "quantity": 90,
            "price": 28,
            "description": "Premium Stock",
        },
        worker_a_task=(
            "Inspect the CURRENT product price. "
            "If the current price is at least 25, "
            "set the description to exactly "
            "'High Value Item'. If the current "
            "price is below 25, stop without "
            "modifying the resource. Preserve "
            "quantity and price."
        ),
        worker_b_task=(
            "Set the product price to exactly 18. " "Preserve quantity and description."
        ),
        worker_a_operation=OperationSpec(
            operation="set",
            field="description",
            value="High Value Item",
        ),
        worker_b_operation=OperationSpec(
            operation="set",
            field="price",
            value=18,
        ),
        # Initial price 28 => stale A would write.
        # B changes price to 18.
        # Fresh A must STOP.
        expected_final={
            "quantity": 90,
            "price": 18,
            "description": "Premium Stock",
        },
    ),
    # =====================================================
    # DISRUPTIVE 3
    #
    # Description controls quantity decision.
    # =====================================================
    BenchmarkScenario(
        scenario_id=("ho_d_description_controls_quantity"),
        name=("Held-out description dependency"),
        semantic_ground_truth=("disruptive"),
        initial_value={
            "quantity": 75,
            "price": 21,
            "description": "Clearance Item",
        },
        worker_a_task=(
            "Inspect the CURRENT product description. "
            "Only if the current description is "
            "exactly 'Clearance Item', set inventory "
            "quantity to exactly 30. If the current "
            "description is anything else, stop "
            "without modifying the resource. "
            "Preserve price and description."
        ),
        worker_b_task=(
            "Set the product description to exactly "
            "'Standard Item'. Preserve quantity "
            "and price."
        ),
        worker_a_operation=OperationSpec(
            operation="set",
            field="quantity",
            value=30,
        ),
        worker_b_operation=OperationSpec(
            operation="set",
            field="description",
            value="Standard Item",
        ),
        # Initial description makes A write.
        # B changes description.
        # Fresh A must STOP.
        expected_final={
            "quantity": 75,
            "price": 21,
            "description": "Standard Item",
        },
    ),
    # =====================================================
    # DISRUPTIVE 4
    #
    # Arithmetic dependency on CURRENT price.
    # =====================================================
    BenchmarkScenario(
        scenario_id=("ho_d_reduce_current_price_by_8"),
        name=("Held-out current price arithmetic"),
        semantic_ground_truth=("disruptive"),
        initial_value={
            "quantity": 120,
            "price": 29,
            "description": "Regular Item",
        },
        worker_a_task=(
            "Reduce the CURRENT product price by "
            "exactly 8. Calculate the new price "
            "from the current price at the time "
            "of the decision. Preserve quantity "
            "and description."
        ),
        worker_b_task=(
            "Set the product price to exactly 21. " "Preserve quantity and description."
        ),
        worker_a_operation=OperationSpec(
            operation="subtract",
            field="price",
            amount=8,
        ),
        worker_b_operation=OperationSpec(
            operation="set",
            field="price",
            value=21,
        ),
        # stale A: 29 - 8 = 21
        # B: 21
        # fresh A: 21 - 8 = 13
        expected_final={
            "quantity": 120,
            "price": 13,
            "description": "Regular Item",
        },
    ),
    # =====================================================
    # DISRUPTIVE 5
    #
    # Quantity threshold controls description.
    # =====================================================
    BenchmarkScenario(
        scenario_id=("ho_d_quantity_threshold_controls_description"),
        name=("Held-out quantity threshold dependency"),
        semantic_ground_truth=("disruptive"),
        initial_value={
            "quantity": 40,
            "price": 17,
            "description": "Warehouse Item",
        },
        worker_a_task=(
            "Inspect the CURRENT inventory quantity. "
            "If the current quantity is 50 or less, "
            "set the product description to exactly "
            "'Low Stock Item'. If the current "
            "quantity is greater than 50, stop "
            "without modifying the resource. "
            "Preserve quantity and price."
        ),
        worker_b_task=(
            "Set inventory quantity to exactly 90. " "Preserve price and description."
        ),
        worker_a_operation=OperationSpec(
            operation="set",
            field="description",
            value="Low Stock Item",
        ),
        worker_b_operation=OperationSpec(
            operation="set",
            field="quantity",
            value=90,
        ),
        # Initial q=40 => stale A would write.
        # B => q=90.
        # Fresh A must STOP.
        expected_final={
            "quantity": 90,
            "price": 17,
            "description": "Warehouse Item",
        },
    ),
]
