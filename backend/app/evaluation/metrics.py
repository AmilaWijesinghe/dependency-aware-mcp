from langchain_core.callbacks import (
    get_usage_metadata_callback,
)

from app.evaluation.schemas import (
    TokenUsage,
)
import asyncio
from functools import wraps


async def gather_completed(*awaitables):
    """Join sibling work even on failure so usage and cleanup finish before return."""
    tasks = [asyncio.create_task(awaitable) for awaitable in awaitables]
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    errors = [result for result in results if isinstance(result, BaseException)]
    if errors:
        if len(errors) > 1:
            raise RuntimeError("; concurrent error: ".join(map(str, errors))) from errors[0]
        raise errors[0]
    return results


def preserve_failure_usage(function):
    """Capture real model callback usage even when no protocol result is returned."""
    @wraps(function)
    async def wrapped(*args, **kwargs):
        with get_usage_metadata_callback() as callback:
            result = await function(*args, **kwargs)
        if result.error:
            usage = aggregate_callback_usage(callback.usage_metadata)
            result.input_tokens = max(result.input_tokens, usage.input_tokens)
            result.output_tokens = max(result.output_tokens, usage.output_tokens)
            result.total_tokens = max(result.total_tokens, usage.total_tokens)
        return result
    return wrapped


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
