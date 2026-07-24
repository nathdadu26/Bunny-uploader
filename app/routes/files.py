import math
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.database import videos_collection
from app.core import bunny, r2

router = APIRouter(prefix="/api/files", tags=["files"])


def _serialize(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "mapping": doc["mapping"],
        "title": doc.get("title") or doc.get("custom_filename") or "",
        "status": doc.get("status", "PROCESSING"),
        "thumbnail": doc.get("thumbnail"),
        "folder": doc.get("folder"),
        "views": doc.get("views", 0),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "error_reason": doc.get("error_reason"),
        "error_stage": doc.get("error_stage"),
    }


@router.get("")
async def list_files(
    page: int = Query(1, ge=1),
    folder: str | None = None,
    status: str | None = None,
    search: str | None = None,
):
    page_size = settings.FILES_PAGE_SIZE
    query: dict = {}
    if folder:
        query["folder"] = folder
    if status:
        query["status"] = status
    if search:
        query["title"] = {"$regex": search, "$options": "i"}

    total = await videos_collection.count_documents(query)
    cursor = (
        videos_collection.find(query)
        .sort("created_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_serialize(doc) async for doc in cursor]

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, math.ceil(total / page_size)),
    }


def _oid(video_id: str) -> ObjectId:
    try:
        return ObjectId(video_id)
    except InvalidId:
        raise HTTPException(400, "Invalid video id")


@router.get("/{video_id}")
async def get_file(video_id: str):
    doc = await videos_collection.find_one({"_id": _oid(video_id)})
    if not doc:
        raise HTTPException(404, "Video not found")
    doc["id"] = str(doc.pop("_id"))
    return doc


class EditPayload(BaseModel):
    title: str | None = None
    folder: str | None = None


@router.patch("/{video_id}")
async def edit_file(video_id: str, payload: EditPayload):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await videos_collection.update_one({"_id": _oid(video_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Video not found")
    return {"ok": True}


@router.delete("/{video_id}")
async def delete_file(video_id: str):
    doc = await videos_collection.find_one({"_id": _oid(video_id)})
    if not doc:
        raise HTTPException(404, "Video not found")

    # Best-effort cleanup on both Bunny and R2; DB row is removed regardless.
    try:
        await bunny.delete_video(doc["bunny_video_id"])
    except Exception:  # noqa: BLE001
        pass
    try:
        await r2.delete_prefix(f"videos/{doc['mapping']}/")
    except Exception:  # noqa: BLE001
        pass

    await videos_collection.delete_one({"_id": _oid(video_id)})
    return {"ok": True}


@router.post("/{video_id}/view")
async def increment_view(video_id: str):
    await videos_collection.update_one({"_id": _oid(video_id)}, {"$inc": {"views": 1}})
    return {"ok": True}
