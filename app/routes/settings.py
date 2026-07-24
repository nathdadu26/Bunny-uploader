from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import settings_collection, channels_collection
from app.core import telegram, scheduler

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---------------- Bot token ----------------

class BotTokenPayload(BaseModel):
    bot_token: str


@router.get("/bot")
async def get_bot_settings():
    doc = await settings_collection.find_one({"_id": "bot"})
    return {"bot_token": doc.get("bot_token") if doc else None}


@router.put("/bot")
async def set_bot_settings(payload: BotTokenPayload):
    await settings_collection.update_one(
        {"_id": "bot"}, {"$set": {"bot_token": payload.bot_token}}, upsert=True
    )
    return {"ok": True}


# ---------------- Channels ----------------

class ChannelPayload(BaseModel):
    name: str
    channel_id: str
    interval_minutes: int = 0  # 0 = manual "post now" only
    post_quantity: int = 1
    active: bool = True


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
    }


@router.get("/channels")
async def list_channels():
    items = [_serialize_channel(doc) async for doc in channels_collection.find({})]
    return {"items": items}


@router.post("/channels")
async def create_channel(payload: ChannelPayload):
    doc = payload.model_dump()
    doc["last_posted_at"] = None
    try:
        result = await channels_collection.insert_one(doc)
    except Exception as exc:  # duplicate channel_id, etc.
        raise HTTPException(400, str(exc))
    doc["_id"] = result.inserted_id
    return _serialize_channel(doc)


@router.patch("/channels/{channel_id}")
async def update_channel(channel_id: str, payload: ChannelPayload):
    updates = payload.model_dump()
    result = await channels_collection.update_one({"_id": _oid(channel_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Channel not found")
    return {"ok": True}


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str):
    await channels_collection.delete_one({"_id": _oid(channel_id)})
    return {"ok": True}


@router.get("/channels/{channel_id}/verify-admin")
async def verify_admin(channel_id: str):
    doc = await channels_collection.find_one({"_id": _oid(channel_id)})
    if not doc:
        raise HTTPException(404, "Channel not found")
    result = await telegram.verify_bot_is_admin(doc["channel_id"])
    return result


@router.post("/channels/{channel_id}/post-now")
async def post_now(channel_id: str, quantity: int | None = None):
    doc = await channels_collection.find_one({"_id": _oid(channel_id)})
    if not doc:
        raise HTTPException(404, "Channel not found")
    posted = await scheduler.post_batch_to_channel(doc, quantity=quantity)
    return {"posted": posted}
