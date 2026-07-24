"""
Instead of a manual "add channel" form, channels are registered by simply
forwarding any message from that channel to the bot in a private chat:

  1. User forwards a message from Channel X to the bot (DM).
  2. Telegram sends this bot an Update containing a `message` whose
     `forward_from_chat` field holds the original channel's id + title
     (this is only present when the channel doesn't hide its forward
     source).
  3. We upsert that channel into MongoDB with sensible defaults
     (interval_minutes=0 i.e. manual, post_quantity=1, active=True) and
     reply in the same private chat confirming it was added.

Telegram delivers updates here via a webhook (configured once via
POST /api/settings/bot/setup-webhook, which also runs automatically on
startup if PUBLIC_URL + a bot token are already configured).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.database import channels_collection
from app.core import telegram
from app.core.logs import log_event

router = APIRouter(prefix="/api/telegram", tags=["telegram-webhook"])


@router.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    message = update.get("message")
    if not message:
        return {"ok": True}  # ignore edited_message, channel_post, callback_query, etc.

    reply_chat_id = message.get("chat", {}).get("id")
    forwarded_chat = message.get("forward_from_chat")

    if not forwarded_chat or forwarded_chat.get("type") not in ("channel", "supergroup"):
        if reply_chat_id:
            await telegram.send_message(
                reply_chat_id,
                "⚠️ I couldn't detect a channel in that message. Forward a message "
                "directly from the target channel (not a copy/anonymous forward) "
                "and make sure the channel doesn't hide the forward source.",
            )
        return {"ok": True}

    channel_id = str(forwarded_chat["id"])
    channel_name = forwarded_chat.get("title") or forwarded_chat.get("username") or "Unnamed channel"

    existing = await channels_collection.find_one({"channel_id": channel_id})
    if existing:
        await telegram.send_message(reply_chat_id, f"ℹ️ '{channel_name}' is already added.")
        return {"ok": True}

    await channels_collection.insert_one({
        "name": channel_name,
        "channel_id": channel_id,
        "interval_minutes": 0,  # manual "post now" until the admin sets a schedule in the dashboard
        "post_quantity": 1,
        "active": True,
        "posted_count": 0,
        "failed_count": 0,
        "last_posted_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    await log_event(f"Channel added via forwarded message: '{channel_name}' ({channel_id})", level="success")

    if reply_chat_id:
        await telegram.send_message(
            reply_chat_id,
            f"✅ Channel added: {channel_name}\nMake sure the bot is an admin there, "
            f"then set its posting interval from the dashboard's Settings page.",
        )

    return {"ok": True}
