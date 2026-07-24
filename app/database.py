from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client = AsyncIOMotorClient(settings.MONGO_URI)
db = client[settings.MONGO_DB_NAME]

videos_collection = db["videos"]
settings_collection = db["settings"]          # single-doc collection for telegram/bot settings
channels_collection = db["telegram_channels"]  # one doc per telegram channel
logs_collection = db["logs"]                   # realtime pipeline/telegram log feed for the dashboard terminal


async def ensure_indexes():
    await videos_collection.create_index("mapping", unique=True)
    await videos_collection.create_index("bunny_video_id", unique=True)
    await videos_collection.create_index("status")
    await videos_collection.create_index("created_at")
    await videos_collection.create_index("folder")
    await channels_collection.create_index("channel_id", unique=True)

    # Make `logs` a capped collection so it self-trims and stays fast to
    # tail, without needing a cron job to delete old rows. Capped
    # collections can't be created via create_index, so this only runs
    # once — if the collection already exists (capped or not) this is a
    # no-op.
    existing = await db.list_collection_names()
    if "logs" not in existing:
        await db.create_collection("logs", capped=True, size=5_000_000, max=5000)
    await logs_collection.create_index("created_at")
    await logs_collection.create_index("mapping")
