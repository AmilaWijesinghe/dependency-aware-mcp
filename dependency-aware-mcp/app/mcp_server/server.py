import logging
from datetime import datetime, timezone

from mcp.server import MCPServer
from pymongo import ReturnDocument

from app.storage.mongodb import resources


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


mcp = MCPServer(
    "Dependency Aware Shared State"
)


@mcp.tool()
async def read_shared_resource(
    resource_key: str,
) -> dict:
    """
    Read a shared resource.

    Returns the current value and its version.
    Always use this before modifying a resource.
    """

    resource = await resources.find_one(
        {
            "_id": resource_key
        }
    )

    if resource is None:
        logger.warning(
            "READ NOT FOUND resource=%s",
            resource_key,
        )

        return {
            "status": "not_found",
            "resource_key": resource_key,
        }

    logger.info(
        "READ resource=%s version=%s",
        resource_key,
        resource["version"],
    )

    return {
        "status": "ok",
        "resource_key": resource_key,
        "value": resource["value"],
        "version": resource["version"],
    }


@mcp.tool()
async def write_shared_resource(
    resource_key: str,
    new_value: dict,
    expected_version: int,
) -> dict:
    """
    Update a shared resource.

    The write succeeds only if expected_version matches
    the current resource version.
    """

    now = datetime.now(timezone.utc)

    updated = await resources.find_one_and_update(
        {
            "_id": resource_key,
            "version": expected_version,
        },
        {
            "$set": {
                "value": new_value,
                "updatedAt": now,
            },
            "$inc": {
                "version": 1,
            },
        },
        return_document=ReturnDocument.AFTER,
    )

    if updated is not None:
        logger.info(
            "WRITE resource=%s expected=%s new_version=%s",
            resource_key,
            expected_version,
            updated["version"],
        )

        return {
            "status": "ok",
            "resource_key": resource_key,
            "previous_version": expected_version,
            "version": updated["version"],
            "value": updated["value"],
        }

    current = await resources.find_one(
        {
            "_id": resource_key
        },
        {
            "version": 1
        },
    )

    if current is None:
        return {
            "status": "not_found",
            "resource_key": resource_key,
        }

    logger.warning(
        "VERSION CONFLICT resource=%s expected=%s actual=%s",
        resource_key,
        expected_version,
        current["version"],
    )

    return {
        "status": "conflict",
        "resource_key": resource_key,
        "expected_version": expected_version,
        "current_version": current["version"],
    }


@mcp.tool()
async def list_shared_resources() -> list[dict]:
    """
    List the shared resources available to the agent.
    """

    cursor = resources.find(
        {},
        {
            "_id": 1,
            "version": 1,
        },
    )

    documents = await cursor.to_list(length=100)

    return [
        {
            "resource_key": document["_id"],
            "version": document["version"],
        }
        for document in documents
    ]


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8001,
    )