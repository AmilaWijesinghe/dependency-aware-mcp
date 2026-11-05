from pymongo import AsyncMongoClient, ASCENDING, DESCENDING

from app.config import settings

client = AsyncMongoClient(settings.mongodb_uri)

db = client[settings.mongodb_database]


# ---------------------------------------------------------
# Collections
# ---------------------------------------------------------

resources = db["resources"]

access_logs = db["access_logs"]

dependencies = db["dependencies"]

conflicts = db["conflicts"]

node_executions = db["node_executions"]

resource_locks = db["resource_locks"]

benchmark_runs = db["benchmark_runs"]

benchmark_results = db["benchmark_results"]
# ---------------------------------------------------------
# Database lifecycle
# ---------------------------------------------------------


async def ping_database() -> None:
    await client.admin.command("ping")


async def ensure_indexes() -> None:
    """
    Create indexes used by the research middleware.
    """

    await node_executions.create_index(
        [
            ("runId", ASCENDING),
            ("agentId", ASCENDING),
            ("nodeId", ASCENDING),
            ("startedAt", DESCENDING),
        ]
    )

    await access_logs.create_index(
        [
            ("runId", ASCENDING),
            ("timestamp", ASCENDING),
        ]
    )

    await access_logs.create_index(
        [
            ("runId", ASCENDING),
            ("agentId", ASCENDING),
        ]
    )

    await dependencies.create_index(
        [
            ("runId", ASCENDING),
            ("resourceKey", ASCENDING),
        ]
    )

    await dependencies.create_index(
        [
            ("runId", ASCENDING),
            ("nodeId", ASCENDING),
        ]
    )

    await conflicts.create_index(
        [
            ("runId", ASCENDING),
            ("timestamp", ASCENDING),
        ]
    )

    await conflicts.create_index(
        [
            ("resourceKey", ASCENDING),
            ("timestamp", DESCENDING),
        ]
    )

    await resource_locks.create_index(
        "expiresAt",
        expireAfterSeconds=0,
    )

    await benchmark_runs.create_index(
        [
            ("benchmarkId", ASCENDING),
            ("startedAt", DESCENDING),
        ]
    )

    await benchmark_results.create_index(
        [
            ("benchmarkId", ASCENDING),
            ("protocol", ASCENDING),
            ("scenarioId", ASCENDING),
        ]
    )

    await benchmark_results.create_index(
        [
            ("runId", ASCENDING),
        ],
        unique=True,
    )


async def close_database() -> None:
    await client.close()
