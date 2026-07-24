from fastapi import APIRouter, Query
from app.database import logs_collection

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _serialize(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "created_at": doc.get("created_at"),
        "level": doc.get("level", "info"),
        "mapping": doc.get("mapping"),
        "message": doc.get("message"),
    }


@router.get("")
async def list_logs(since: str | None = Query(None), limit: int = Query(200, le=1000)):
    """
    Polled every couple of seconds by the Overview page's live terminal.
    Pass `since` (an ISO timestamp from the last batch received) to get
    only newer entries; omit it to get the most recent `limit` entries.
    """
    query = {}
    if since:
        query["created_at"] = {"$gt": since}

    cursor = logs_collection.find(query).sort("created_at", 1 if since else -1).limit(limit)
    items = [_serialize(doc) async for doc in cursor]
    if not since:
        items.reverse()  # keep chronological order for initial load too
    return {"items": items}
