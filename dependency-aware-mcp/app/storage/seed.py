"""Idempotent administrative example seed; existing state is never reset."""

import asyncio
import logging

from app.concurrency.conflicts import ResourceNotFound
from app.config import Settings
from app.storage import repositories
from app.storage.database import Database, init_db

logger = logging.getLogger(__name__)


async def seed_example() -> None:
    database = Database(Settings().database_path)
    await init_db(database.path)
    async with database.transaction() as connection:
        try:
            resource = await repositories.get_resource(connection, "inventory/product_1")
        except ResourceNotFound:
            resource = await repositories.create_resource(
                connection,
                "inventory/product_1",
                {"quantity": 100, "price": 20, "description": "Product A"},
            )
    logger.info("Example ready: %s@v%s", resource.resource_key, resource.version)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_example())
