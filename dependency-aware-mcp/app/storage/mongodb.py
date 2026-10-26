from pymongo import AsyncMongoClient

from app.config import settings


client = AsyncMongoClient(
    settings.mongodb_uri
)

db = client[
    settings.mongodb_database
]

resources = db["resources"]


async def ping_database() -> None:
    await client.admin.command("ping")


async def close_database() -> None:
    await client.close()