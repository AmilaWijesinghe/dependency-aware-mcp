from copy import deepcopy

from app.evaluation.schemas import (
    BenchmarkScenario,
    OperationSpec,
)


def apply_operation(
    value: dict,
    operation: OperationSpec,
) -> dict:
    """
    Deterministic helper used only for ground-truth
    reasoning/tests.

    The LLM workers do not use this function to make
    their decisions.
    """

    result = deepcopy(value)

    if operation.operation == "set":

        result[
            operation.field
        ] = operation.value

        return result

    if operation.operation == "subtract":

        amount = operation.amount

        if amount is None:
            raise ValueError(
                "subtract operation requires amount"
            )

        current = result[
            operation.field
        ]

        if current < amount:
            raise ValueError(
                "Insufficient value for subtraction"
            )

        result[
            operation.field
        ] = (
            current - amount
        )

        return result

    raise ValueError(
        f"Unknown operation: "
        f"{operation.operation}"
    )


INITIAL_VALUE = {
    "quantity": 100,
    "price": 20,
    "description": "Test Product",
}


# =========================================================
# FINAL EVALUATION SCENARIOS
#
# 5 NON-DISRUPTIVE
# 5 DISRUPTIVE
# =========================================================

SCENARIOS = [

    # =====================================================
    # NON-DISRUPTIVE 1
    # =====================================================

    BenchmarkScenario(
        scenario_id=(
            "nd_price_vs_quantity"
        ),

        name=(
            "Price update independent "
            "of quantity update"
        ),

        semantic_ground_truth=(
            "non_disruptive"
        ),

        initial_value=(
            INITIAL_VALUE.copy()
        ),

        worker_a_task=(
            "Set the product price to exactly 25. "
            "This price decision is independent of "
            "inventory quantity. Preserve quantity "
            "and description."
        ),

        worker_b_task=(
            "Set the product quantity to exactly 60. "
            "Preserve price and description."
        ),

        worker_a_operation=(
            OperationSpec(
                operation="set",
                field="price",
                value=25,
            )
        ),

        worker_b_operation=(
            OperationSpec(
                operation="set",
                field="quantity",
                value=60,
            )
        ),

        expected_final={
            "quantity": 60,
            "price": 25,
            "description":
                "Test Product",
        },
    ),

    # =====================================================
    # NON-DISRUPTIVE 2
    # =====================================================

    BenchmarkScenario(
        scenario_id=(
            "nd_description_vs_quantity"
        ),

        name=(
            "Description update independent "
            "of quantity"
        ),

        semantic_ground_truth=(
            "non_disruptive"
        ),

        initial_value=(
            INITIAL_VALUE.copy()
        ),

        worker_a_task=(
            "Set the product description to exactly "
            "'Featured Product'. This decision is "
            "independent of inventory quantity and "
            "price. Preserve all other fields."
        ),

        worker_b_task=(
            "Set the product quantity to exactly 70. "
            "Preserve price and description."
        ),

        worker_a_operation=(
            OperationSpec(
                operation="set",
                field="description",
                value="Featured Product",
            )
        ),

        worker_b_operation=(
            OperationSpec(
                operation="set",
                field="quantity",
                value=70,
            )
        ),

        expected_final={
            "quantity": 70,
            "price": 20,
            "description":
                "Featured Product",
        },
    ),

    # =====================================================
    # NON-DISRUPTIVE 3
    # =====================================================

    BenchmarkScenario(
        scenario_id=(
            "nd_price_vs_description"
        ),

        name=(
            "Price update independent "
            "of description update"
        ),

        semantic_ground_truth=(
            "non_disruptive"
        ),

        initial_value=(
            INITIAL_VALUE.copy()
        ),

        worker_a_task=(
            "Set the product price to exactly 18. "
            "This price decision is independent of "
            "the product description and quantity. "
            "Preserve all other fields."
        ),

        worker_b_task=(
            "Set the product description to exactly "
            "'Updated Packaging'. Preserve quantity "
            "and price."
        ),

        worker_a_operation=(
            OperationSpec(
                operation="set",
                field="price",
                value=18,
            )
        ),

        worker_b_operation=(
            OperationSpec(
                operation="set",
                field="description",
                value="Updated Packaging",
            )
        ),

        expected_final={
            "quantity": 100,
            "price": 18,
            "description":
                "Updated Packaging",
        },
    ),

    # =====================================================
    # NON-DISRUPTIVE 4
    # =====================================================

    BenchmarkScenario(
        scenario_id=(
            "nd_quantity_vs_price"
        ),

        name=(
            "Fixed quantity update independent "
            "of price update"
        ),

        semantic_ground_truth=(
            "non_disruptive"
        ),

        initial_value=(
            INITIAL_VALUE.copy()
        ),

        worker_a_task=(
            "Set inventory quantity to exactly 80. "
            "This is a fixed target and does not "
            "depend on product price. Preserve price "
            "and description."
        ),

        worker_b_task=(
            "Set product price to exactly 22. "
            "Preserve quantity and description."
        ),

        worker_a_operation=(
            OperationSpec(
                operation="set",
                field="quantity",
                value=80,
            )
        ),

        worker_b_operation=(
            OperationSpec(
                operation="set",
                field="price",
                value=22,
            )
        ),

        expected_final={
            "quantity": 80,
            "price": 22,
            "description":
                "Test Product",
        },
    ),

    # =====================================================
    # NON-DISRUPTIVE 5
    # =====================================================

    BenchmarkScenario(
        scenario_id=(
            "nd_description_vs_price"
        ),

        name=(
            "Description update independent "
            "of price update"
        ),

        semantic_ground_truth=(
            "non_disruptive"
        ),

        initial_value=(
            INITIAL_VALUE.copy()
        ),

        worker_a_task=(
            "Set the product description to exactly "
            "'Premium Product'. This description "
            "decision is independent of product price "
            "and inventory quantity."
        ),

        worker_b_task=(
            "Set product price to exactly 30. "
            "Preserve quantity and description."
        ),

        worker_a_operation=(
            OperationSpec(
                operation="set",
                field="description",
                value="Premium Product",
            )
        ),

        worker_b_operation=(
            OperationSpec(
                operation="set",
                field="price",
                value=30,
            )
        ),

        expected_final={
            "quantity": 100,
            "price": 30,
            "description":
                "Premium Product",
        },
    ),

    # =====================================================
    # DISRUPTIVE 1
    #
    # Existing allocation example.
    # =====================================================

    BenchmarkScenario(
        scenario_id=(
            "d_allocate_30_after_quantity_change"
        ),

        name=(
            "Allocation depends on changed inventory"
        ),

        semantic_ground_truth=(
            "disruptive"
        ),

        initial_value=(
            INITIAL_VALUE.copy()
        ),

        worker_a_task=(
            "Allocate exactly 30 units from the "
            "CURRENT inventory quantity. Allocation "
            "means subtract 30 from the current "
            "quantity. If fewer than 30 units are "
            "available, stop without writing. Preserve "
            "price and description."
        ),

        worker_b_task=(
            "Set inventory quantity to exactly 60. "
            "Preserve price and description."
        ),

        worker_a_operation=(
            OperationSpec(
                operation="subtract",
                field="quantity",
                amount=30,
            )
        ),

        worker_b_operation=(
            OperationSpec(
                operation="set",
                field="quantity",
                value=60,
            )
        ),

        expected_final={
            "quantity": 30,
            "price": 20,
            "description":
                "Test Product",
        },
    ),

    # =====================================================
    # DISRUPTIVE 2
    #
    # Concurrent change makes operation impossible.
    # =====================================================

    BenchmarkScenario(
        scenario_id=(
            "d_allocation_becomes_impossible"
        ),

        name=(
            "Concurrent change makes allocation "
            "impossible"
        ),

        semantic_ground_truth=(
            "disruptive"
        ),

        initial_value=(
            INITIAL_VALUE.copy()
        ),

        worker_a_task=(
            "Allocate exactly 50 units from the "
            "CURRENT inventory quantity. Subtract 50 "
            "only if at least 50 units are currently "
            "available. If fewer than 50 units are "
            "available, stop and do not write. "
            "Preserve price and description."
        ),

        worker_b_task=(
            "Set inventory quantity to exactly 40. "
            "Preserve price and description."
        ),

        worker_a_operation=(
            OperationSpec(
                operation="subtract",
                field="quantity",
                amount=50,
            )
        ),

        worker_b_operation=(
            OperationSpec(
                operation="set",
                field="quantity",
                value=40,
            )
        ),

        # After B:
        #
        # quantity = 40
        #
        # A must STOP because 40 < 50.
        expected_final={
            "quantity": 40,
            "price": 20,
            "description":
                "Test Product",
        },
    ),

    # =====================================================
    # DISRUPTIVE 3
    #
    # Cross-field dependency:
    # quantity determines whether price can change.
    # =====================================================

    BenchmarkScenario(
        scenario_id=(
            "d_quantity_threshold_controls_price"
        ),

        name=(
            "Quantity threshold controls "
            "price decision"
        ),

        semantic_ground_truth=(
            "disruptive"
        ),

        initial_value=(
            INITIAL_VALUE.copy()
        ),

        worker_a_task=(
            "Inspect the CURRENT inventory quantity. "
            "If the current quantity is at least 80, "
            "set the price to exactly 18. If the "
            "current quantity is below 80, stop and "
            "do not modify the resource. Preserve "
            "quantity and description."
        ),

        worker_b_task=(
            "Set inventory quantity to exactly 60. "
            "Preserve price and description."
        ),

        worker_a_operation=(
            OperationSpec(
                operation="set",
                field="price",
                value=18,
            )
        ),

        worker_b_operation=(
            OperationSpec(
                operation="set",
                field="quantity",
                value=60,
            )
        ),

        # Initially quantity=100 so stale A would
        # choose price=18.
        #
        # After B quantity=60, A must STOP.
        expected_final={
            "quantity": 60,
            "price": 20,
            "description":
                "Test Product",
        },
    ),

    # =====================================================
    # DISRUPTIVE 4
    #
    # Cross-field semantic dependency:
    # description controls price decision.
    # =====================================================

    BenchmarkScenario(
        scenario_id=(
            "d_description_controls_price"
        ),

        name=(
            "Description change invalidates "
            "price decision"
        ),

        semantic_ground_truth=(
            "disruptive"
        ),

        initial_value=(
            INITIAL_VALUE.copy()
        ),

        worker_a_task=(
            "Inspect the CURRENT product description. "
            "Only if the description is exactly "
            "'Test Product', set the price to exactly "
            "25. If the current description is "
            "anything else, stop and do not modify "
            "the resource. Preserve quantity and "
            "description."
        ),

        worker_b_task=(
            "Set the product description to exactly "
            "'Discontinued Product'. Preserve "
            "quantity and price."
        ),

        worker_a_operation=(
            OperationSpec(
                operation="set",
                field="price",
                value=25,
            )
        ),

        worker_b_operation=(
            OperationSpec(
                operation="set",
                field="description",
                value="Discontinued Product",
            )
        ),

        expected_final={
            "quantity": 100,
            "price": 20,
            "description":
                "Discontinued Product",
        },
    ),

    # =====================================================
    # DISRUPTIVE 5
    #
    # Same-field arithmetic dependency.
    # =====================================================

    BenchmarkScenario(
        scenario_id=(
            "d_reduce_current_price"
        ),

        name=(
            "Price calculation depends on "
            "current price"
        ),

        semantic_ground_truth=(
            "disruptive"
        ),

        initial_value=(
            INITIAL_VALUE.copy()
        ),

        worker_a_task=(
            "Reduce the CURRENT product price by "
            "exactly 5. Calculate the new price from "
            "the current price at the time you make "
            "the decision. Preserve quantity and "
            "description."
        ),

        worker_b_task=(
            "Set the product price to exactly 12. "
            "Preserve quantity and description."
        ),

        worker_a_operation=(
            OperationSpec(
                operation="subtract",
                field="price",
                amount=5,
            )
        ),

        worker_b_operation=(
            OperationSpec(
                operation="set",
                field="price",
                value=12,
            )
        ),

        # B: price -> 12
        # A fresh reasoning: 12 - 5 = 7
        expected_final={
            "quantity": 100,
            "price": 7,
            "description":
                "Test Product",
        },
    ),
]