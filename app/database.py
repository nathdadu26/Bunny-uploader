from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client = AsyncIOMotorClient(settings.MONGO_URI)
db = client[settings.MONGO_DB_NAME]

videos_collection = db["videos"]
settings_collection = db["settings"]          # single-doc collection for telegram/bot settings
channels_collection = db["telegram_channels"]  # one doc per telegram channel


async def ensure_indexes():
    await videos_collection.create_index("mapping", unique=True)
    await videos_collection.create_index("bunny_video_id", unique=True)
    await videos_collection.create_index("status")
    await videos_collection.create_index("created_at")
    await videos_collection.create_index("folder")
    await channels_collection.create_index("channel_id", unique=True)
