import asyncio
from datetime import datetime, timezone

from app.storage.mongodb import (
    close_database,
    ping_database,
    resources,
)


async def main() -> None:
    await ping_database()

    print("MongoDB connected successfully.")

    now = datetime.now(timezone.utc)

    await resources.replace_one(
        {"_id": "inventory/product_1"},
        {
            "_id": "inventory/product_1",
            "value": {
                "quantity": 100,
                "price": 20,
                "description": "Test Product",
            },
            "version": 1,
            "createdAt": now,
            "updatedAt": now,
        },
        upsert=True,
    )

    resource = await resources.find_one({"_id": "inventory/product_1"})

    print("\nCreated/reset resource:")
    print(resource)

    await close_database()


if __name__ == "__main__":
    asyncio.run(main())
