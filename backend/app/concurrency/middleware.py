import logging

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.storage.mongodb import (
    resource_locks,
    resources,
)

from app.storage.repositories import (
    ProvenanceRepository,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Trace context
# ---------------------------------------------------------


@dataclass(frozen=True)
class ResearchTraceContext:
    run_id: str
    agent_id: str
    node_id: str
    request_id: str


def _normalise_headers(
    headers: Mapping[str, str] | None,
) -> dict[str, str]:

    if headers is None:
        return {}

    return {key.lower(): value for key, value in headers.items()}


def get_research_trace(
    ctx: Context,
) -> ResearchTraceContext:
    """
    Extract research correlation metadata from the MCP
    HTTP request.

    These headers are supplied by our controlled test
    harness, not by the LLM.
    """

    headers = _normalise_headers(ctx.headers)

    run_id = headers.get("x-research-run-id")

    agent_id = headers.get("x-research-agent-id")

    node_id = headers.get("x-research-node-id")

    missing = []

    if not run_id:
        missing.append("X-Research-Run-Id")

    if not agent_id:
        missing.append("X-Research-Agent-Id")

    if not node_id:
        missing.append("X-Research-Node-Id")

    if missing:
        raise ToolError("Missing research trace headers: " + ", ".join(missing))

    return ResearchTraceContext(
        run_id=run_id,
        agent_id=agent_id,
        node_id=node_id,
        request_id=str(ctx.request_id),
    )


# ---------------------------------------------------------
# Middleware
# ---------------------------------------------------------


class ConcurrencyMiddleware:

    def __init__(self) -> None:
        self.provenance = ProvenanceRepository()

    # -----------------------------------------------------
    # READ
    # -----------------------------------------------------

    async def read_shared_resource(
        self,
        *,
        resource_key: str,
        ctx: Context,
    ) -> dict:

        trace = get_research_trace(ctx)

        resource = await resources.find_one({"_id": resource_key})

        if resource is None:
            return {
                "status": "not_found",
                "resource_key": resource_key,
            }

        value = resource["value"]
        version = resource["version"]

        # Record access + dependency.
        await self.provenance.record_read(
            run_id=trace.run_id,
            agent_id=trace.agent_id,
            node_id=trace.node_id,
            request_id=trace.request_id,
            resource_key=resource_key,
            version=version,
            value_snapshot=value,
        )

        logger.info(
            ("READ " "run=%s agent=%s node=%s " "resource=%s version=%s"),
            trace.run_id,
            trace.agent_id,
            trace.node_id,
            resource_key,
            version,
        )

        return {
            "status": "ok",
            "resource_key": resource_key,
            "value": value,
            "version": version,
        }

    # -----------------------------------------------------
    # WRITE
    # -----------------------------------------------------

    async def write_shared_resource(
        self,
        *,
        resource_key: str,
        new_value: dict,
        expected_version: int,
        ctx: Context,
    ) -> dict:

        trace = get_research_trace(ctx)

        now = datetime.now(timezone.utc)

        # IMPORTANT:
        # OCC validation and mutation happen atomically.
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
            return_document=(ReturnDocument.AFTER),
        )

        # -------------------------------------------------
        # Successful write
        # -------------------------------------------------

        if updated is not None:

            new_version = updated["version"]

            await self.provenance.record_write(
                run_id=trace.run_id,
                agent_id=trace.agent_id,
                node_id=trace.node_id,
                request_id=(trace.request_id),
                resource_key=(resource_key),
                previous_version=(expected_version),
                new_version=(new_version),
                value_snapshot=(updated["value"]),
            )

            logger.info(
                (
                    "WRITE SUCCESS "
                    "run=%s agent=%s node=%s "
                    "resource=%s "
                    "expected=%s new=%s"
                ),
                trace.run_id,
                trace.agent_id,
                trace.node_id,
                resource_key,
                expected_version,
                new_version,
            )

            return {
                "status": "ok",
                "resource_key": resource_key,
                "previous_version": expected_version,
                "version": new_version,
                "value": updated["value"],
            }

        # -------------------------------------------------
        # Failed conditional write
        # -------------------------------------------------

        current = await resources.find_one({"_id": resource_key})

        if current is None:
            return {
                "status": "not_found",
                "resource_key": resource_key,
            }

        actual_version = current["version"]

        # Record the conflict.
        await self.provenance.record_conflict(
            run_id=trace.run_id,
            agent_id=trace.agent_id,
            node_id=trace.node_id,
            request_id=(trace.request_id),
            resource_key=(resource_key),
            expected_version=(expected_version),
            actual_version=(actual_version),
            attempted_value=(new_value),
            current_value=(current["value"]),
        )

        logger.warning(
            (
                "VERSION CONFLICT "
                "run=%s agent=%s node=%s "
                "resource=%s "
                "expected=%s actual=%s"
            ),
            trace.run_id,
            trace.agent_id,
            trace.node_id,
            resource_key,
            expected_version,
            actual_version,
        )

        return {
            "status": "conflict",
            "resource_key": resource_key,
            "expected_version": expected_version,
            "current_version": actual_version,
        }

    async def naive_write_shared_resource(
        self,
        *,
        resource_key: str,
        new_value: dict,
        ctx: Context,
    ) -> dict:
        """
        Naive baseline.

        Writes regardless of whether another agent changed
        the resource after this worker read it.
        """

        trace = get_research_trace(ctx)

        updated = await resources.find_one_and_update(
            {"_id": resource_key},
            {
                "$set": {
                    "value": new_value,
                    "updatedAt": datetime.now(timezone.utc),
                },
                "$inc": {
                    "version": 1,
                },
            },
            return_document=ReturnDocument.AFTER,
        )

        if updated is None:
            return {
                "status": "not_found",
                "resource_key": resource_key,
            }

        previous_version = updated["version"] - 1

        await self.provenance.record_write(
            run_id=trace.run_id,
            agent_id=trace.agent_id,
            node_id=trace.node_id,
            request_id=trace.request_id,
            resource_key=resource_key,
            previous_version=previous_version,
            new_version=updated["version"],
            value_snapshot=updated["value"],
        )

        logger.info(
            ("NAIVE WRITE " "run=%s agent=%s node=%s " "resource=%s new_version=%s"),
            trace.run_id,
            trace.agent_id,
            trace.node_id,
            resource_key,
            updated["version"],
        )

        return {
            "status": "ok",
            "resource_key": resource_key,
            "previous_version": previous_version,
            "version": updated["version"],
            "value": updated["value"],
        }

    async def acquire_resource_lock(
        self,
        *,
        resource_key: str,
        ctx: Context,
        lease_seconds: int = 30,
    ) -> dict:
        """
        Application-level pessimistic lock.

        Lock ownership is derived from the MCP request headers,
        not generated by the LLM.
        """

        trace = get_research_trace(ctx)

        now = datetime.now(timezone.utc)

        expires_at = now + timedelta(seconds=lease_seconds)

        # Remove an expired lock ourselves.
        #
        # We do not depend on MongoDB TTL timing for
        # correctness.
        await resource_locks.delete_one(
            {
                "_id": resource_key,
                "expiresAt": {"$lte": now},
            }
        )

        try:
            await resource_locks.insert_one(
                {
                    "_id": resource_key,
                    "ownerRunId": trace.run_id,
                    "ownerAgentId": trace.agent_id,
                    "ownerNodeId": trace.node_id,
                    "acquiredAt": now,
                    "expiresAt": expires_at,
                }
            )

        except DuplicateKeyError:

            current_lock = await resource_locks.find_one({"_id": resource_key})

            return {
                "status": "busy",
                "resource_key": resource_key,
                "owner_agent": (
                    current_lock.get("ownerAgentId") if current_lock else None
                ),
            }

        logger.info(
            ("LOCK ACQUIRED " "run=%s agent=%s " "resource=%s"),
            trace.run_id,
            trace.agent_id,
            resource_key,
        )

        return {
            "status": "acquired",
            "resource_key": resource_key,
        }

    async def release_resource_lock(
        self,
        *,
        resource_key: str,
        ctx: Context,
    ) -> dict:

        trace = get_research_trace(ctx)

        result = await resource_locks.delete_one(
            {
                "_id": resource_key,
                "ownerRunId": trace.run_id,
                "ownerAgentId": trace.agent_id,
            }
        )

        if result.deleted_count == 0:
            return {
                "status": "not_owner",
                "resource_key": resource_key,
            }

        logger.info(
            ("LOCK RELEASED " "run=%s agent=%s " "resource=%s"),
            trace.run_id,
            trace.agent_id,
            resource_key,
        )

        return {
            "status": "released",
            "resource_key": resource_key,
        }

    async def locked_write_shared_resource(
        self,
        *,
        resource_key: str,
        new_value: dict,
        ctx: Context,
    ) -> dict:
        """
        Write used by the application-level pessimistic
        locking baseline.

        The caller must currently own the resource lock.
        """

        trace = get_research_trace(ctx)

        now = datetime.now(timezone.utc)

        lock = await resource_locks.find_one(
            {
                "_id": resource_key,
                "ownerRunId": trace.run_id,
                "ownerAgentId": trace.agent_id,
                "expiresAt": {"$gt": now},
            }
        )

        if lock is None:

            return {
                "status": "lock_required",
                "resource_key": resource_key,
            }

        updated = await resources.find_one_and_update(
            {"_id": resource_key},
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

        if updated is None:
            return {
                "status": "not_found",
                "resource_key": resource_key,
            }

        previous_version = updated["version"] - 1

        await self.provenance.record_write(
            run_id=trace.run_id,
            agent_id=trace.agent_id,
            node_id=trace.node_id,
            request_id=trace.request_id,
            resource_key=resource_key,
            previous_version=previous_version,
            new_version=updated["version"],
            value_snapshot=updated["value"],
        )

        logger.info(
            ("LOCKED WRITE " "run=%s agent=%s " "resource=%s " "version=%s"),
            trace.run_id,
            trace.agent_id,
            resource_key,
            updated["version"],
        )

        return {
            "status": "ok",
            "resource_key": resource_key,
            "previous_version": previous_version,
            "version": updated["version"],
            "value": updated["value"],
        }
