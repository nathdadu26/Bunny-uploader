from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.database import settings_collection, channels_collection
from app.core import telegram, scheduler
from app.core.logs import log_event

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---------------- Bot token ----------------

class BotTokenPayload(BaseModel):
    bot_token: str


@router.get("/bot")
async def get_bot_settings():
    doc = await settings_collection.find_one({"_id": "bot"})
    return {
        "bot_token": doc.get("bot_token") if doc else None,
        "bot_name": doc.get("bot_name") if doc else None,
        "bot_username": doc.get("bot_username") if doc else None,
        "webhook_configured": bool(doc.get("webhook_configured")) if doc else False,
    }


@router.put("/bot")
async def set_bot_settings(payload: BotTokenPayload):
    await settings_collection.update_one(
        {"_id": "bot"}, {"$set": {"bot_token": payload.bot_token}}, upsert=True
    )

    # Immediately verify the token + cache the bot's identity so the
    # Settings page can show "Bot name" without hitting Telegram on every
    # page load.
    bot_name = bot_username = None
    try:
        me = await telegram.get_me()
        bot_name = me.get("first_name")
        bot_username = me.get("username")
        await settings_collection.update_one(
            {"_id": "bot"},
            {"$set": {"bot_name": bot_name, "bot_username": bot_username}},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Could not verify this bot token with Telegram: {exc}")

    # Try to (re)register the webhook automatically now that we have a
    # valid token, so channel-adding-by-forward works right away.
    await _setup_webhook_if_possible()

    return {"ok": True, "bot_name": bot_name, "bot_username": bot_username}


async def _setup_webhook_if_possible():
    if not settings.PUBLIC_URL:
        return
    webhook_url = settings.PUBLIC_URL.rstrip("/") + "/api/telegram/webhook"
    try:
        await telegram.set_webhook(webhook_url)
        await settings_collection.update_one(
            {"_id": "bot"}, {"$set": {"webhook_configured": True}}, upsert=True
        )
        await log_event(f"Telegram webhook registered at {webhook_url}", level="success")
    except Exception as exc:  # noqa: BLE001
        await log_event("Failed to register Telegram webhook", level="error", exc=exc)


@router.post("/bot/setup-webhook")
async def setup_webhook():
    if not settings.PUBLIC_URL:
        raise HTTPException(400, "Set PUBLIC_URL in the environment first (your deployed app's public URL)")
    await _setup_webhook_if_possible()
    return {"ok": True}


@router.get("/bot/stats")
async def bot_stats():
    total_channels = await channels_collection.count_documents({})
    total_posts = 0
    total_failed = 0
    async for doc in channels_collection.find({}, {"posted_count": 1, "failed_count": 1}):
        total_posts += doc.get("posted_count", 0)
        total_failed += doc.get("failed_count", 0)
    return {
        "total_channels": total_channels,
        "total_posts": total_posts,
        "total_failed_posts": total_failed,
    }


# ---------------- Channels ----------------
# Channels are added by forwarding a message to the bot (see
# app/routes/telegram_webhook.py) rather than a manual form. This section
# only supports editing schedule/quantity/active on an existing channel
# and removing one.

class ChannelUpdatePayload(BaseModel):
    interval_minutes: int | None = None
    post_quantity: int | None = None
    active: bool | None = None


def _oid(cid: str) -> ObjectId:
    try:
        return ObjectId(cid)
    except InvalidId:
        raise HTTPException(400, "Invalid channel id")


def _serialize_channel(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "channel_id": doc["channel_id"],
        "interval_minutes": doc.get("interval_minutes", 0),
        "post_quantity": doc.get("post_quantity", 1),
        "active": doc.get("active", True),
        "last_posted_at": doc.get("last_posted_at"),
        "posted_count": doc.get("posted_count", 0),
        "failed_count": doc.get("failed_count", 0),
    }


@router.get("/channels")
async def list_channels():
    items = [_serialize_channel(doc) async for doc in channels_collection.find({}).sort("created_at", -1)]
    return {"items": items}


@router.patch("/channels/{channel_id}")
async def update_channel(channel_id: str, payload: ChannelUpdatePayload):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    result = await channels_collection.update_one({"_id": _oid(channel_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Channel not found")
    return {"ok": True}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str):
    result = await channels_collection.delete_one({"_id": _oid(channel_id)})
    if result.deleted_count == 0:
        raise HTTPException(404, "Channel not found")
    return {"ok": True}


@router.post("/channels/{channel_id}/post-now")
async def post_now(channel_id: str, quantity: int | None = None):
    doc = await channels_collection.find_one({"_id": _oid(channel_id)})
    if not doc:
        raise HTTPException(404, "Channel not found")
    posted = await scheduler.post_batch_to_channel(doc, quantity=quantity)
    return {"posted": posted}
