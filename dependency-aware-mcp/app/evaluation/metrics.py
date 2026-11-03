from langchain_core.callbacks import (
    get_usage_metadata_callback,
)

from app.evaluation.schemas import (
    TokenUsage,
)


def aggregate_callback_usage(
    usage_metadata: dict,
) -> TokenUsage:

    result = TokenUsage()

    for usage in usage_metadata.values():

        result = result + TokenUsage(
            input_tokens=usage.get(
                "input_tokens",
                0,
            ),
            output_tokens=usage.get(
                "output_tokens",
                0,
            ),
            total_tokens=usage.get(
                "total_tokens",
                0,
            ),
        )

    return result
