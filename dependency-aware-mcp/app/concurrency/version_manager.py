"""Versioned resource operations with transactional provenance."""

import logging

from pydantic import JsonValue

from app.concurrency.conflicts import VersionConflict
from app.concurrency.provenance import (
    log_read,
    log_write,
    record_conflict,
    record_dependency,
    require_identity,
)
from app.schemas.resource import SharedResource
from app.storage import repositories
from app.storage.database import Database

logger = logging.getLogger(__name__)


class ResourceService:
    def __init__(self, database: Database):
        self.database = database

    async def read(self, resource_key: str) -> SharedResource:
        identity = require_identity()
        async with self.database.transaction() as connection:
            resource = await repositories.get_resource(connection, resource_key)
            await log_read(connection, identity, resource_key, resource.version)
            await record_dependency(connection, identity, resource_key, resource.version)
        logger.info(
            "run=%s agent=%s node=%s READ %s@v%s",
            identity.run_id, identity.agent_id, identity.node_id,
            resource_key, resource.version,
        )
        return resource

    async def list(self) -> list[SharedResource]:
        identity = require_identity()
        async with self.database.transaction() as connection:
            resources = await repositories.list_resources(connection)
            # Listing exposes values, so each returned snapshot is a dependency.
            for resource in resources:
                await log_read(
                    connection, identity, resource.resource_key, resource.version
                )
                await record_dependency(
                    connection, identity, resource.resource_key, resource.version
                )
        return resources

    async def write(
        self,
        resource_key: str,
        new_value: dict[str, JsonValue],
        expected_version: int,
    ) -> SharedResource:
        """Persist either the mutation plus WRITE, or the conflict, atomically.

        A conflict is raised only after its audit row commits. A provenance
        insertion failure rolls back a successful UPDATE as well.
        """
        identity = require_identity()
        conflict = None
        resource = None
        async with self.database.transaction() as connection:
            try:
                resource = await repositories.update_resource(
                    connection, resource_key, new_value, expected_version
                )
            except VersionConflict as error:
                await record_conflict(connection, identity, error)
                conflict = error
            else:
                await log_write(connection, identity, resource_key, resource.version)
        if conflict is not None:
            logger.warning(
                "run=%s agent=%s node=%s %s",
                identity.run_id, identity.agent_id, identity.node_id, conflict,
            )
            raise conflict
        assert resource is not None
        logger.info(
            "run=%s agent=%s node=%s WRITE %s v%s->v%s",
            identity.run_id, identity.agent_id, identity.node_id,
            resource_key, expected_version, resource.version,
        )
        return resource
