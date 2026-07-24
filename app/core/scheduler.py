import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import channels_collection, videos_collection
from app.core import telegram
from app.core.logs import log_event

logger = logging.getLogger("scheduler")
scheduler = AsyncIOScheduler()


async def _channel_due(channel: dict) -> bool:
    interval = channel.get("interval_minutes", 0)
    if interval <= 0:
        return False  # interval 0 == manual "post now" only, never auto-fires
    last_posted_at = channel.get("last_posted_at")
    if not last_posted_at:
        return True
    last = datetime.fromisoformat(last_posted_at)
    elapsed_minutes = (datetime.now(timezone.utc) - last).total_seconds() / 60
    return elapsed_minutes >= interval


async def post_batch_to_channel(channel: dict, quantity: int | None = None):
    """Posts `quantity` (or channel's post_quantity) READY videos not yet sent to this channel."""
    channel_id = channel["channel_id"]
    qty = quantity or channel.get("post_quantity", 1)

    cursor = videos_collection.find(
        {
            "status": "READY",
            "telegram_posted_channels": {"$ne": channel_id},
        }
    ).sort("created_at", 1).limit(qty)

    posted = 0
    failed = 0
    async for video in cursor:
        try:
            await log_event(
                f"Posting to channel '{channel.get('name')}'...",
                mapping=video.get("mapping"),
            )
            await telegram.post_video_to_channel(
                channel_id=channel_id,
                thumbnail_url=video.get("thumbnail") or "",
                title=video.get("title") or "New video",
                mapping=video["mapping"],
            )
            await videos_collection.update_one(
                {"_id": video["_id"]},
                {"$addToSet": {"telegram_posted_channels": channel_id}},
            )
            await log_event(
                f"Posted to channel '{channel.get('name')}'",
                level="success", mapping=video.get("mapping"),
            )
            posted += 1
        except Exception as exc:  # noqa: BLE001
            await log_event(
                f"Failed to post to channel '{channel.get('name')}'",
                level="error", mapping=video.get("mapping"), exc=exc,
            )
            logger.exception("Failed to post video %s to channel %s", video.get("mapping"), channel_id)
            failed += 1

    update_fields = {"last_posted_at": datetime.now(timezone.utc).isoformat()}
    inc_fields = {}
    if posted:
        inc_fields["posted_count"] = posted
    if failed:
        inc_fields["failed_count"] = failed

    update_op = {"$set": update_fields}
    if inc_fields:
        update_op["$inc"] = inc_fields

    await channels_collection.update_one({"_id": channel["_id"]}, update_op)
    return posted


async def check_all_channels():
    async for channel in channels_collection.find({"active": True}):
        if await _channel_due(channel):
            await post_batch_to_channel(channel)


def start_scheduler():
    scheduler.add_job(check_all_channels, "interval", minutes=1, id="telegram_auto_post", replace_existing=True)
    scheduler.start()
