from fastapi import APIRouter
from app.database import videos_collection

router = APIRouter(prefix="/api/overview", tags=["overview"])


@router.get("")
async def get_overview():
    total_videos = await videos_collection.count_documents({})
    processing_count = await videos_collection.count_documents({"status": "PROCESSING"})
    ready_count = await videos_collection.count_documents({"status": "READY"})
    error_count = await videos_collection.count_documents({"status": "ERROR"})

    total_views = 0
    total_storage_bytes = 0
    async for doc in videos_collection.find({}, {"views": 1, "all_files": 1}):
        total_views += doc.get("views", 0)
        for f in doc.get("all_files", []):
            total_storage_bytes += f.get("size", 0)

    return {
        "total_videos": total_videos,
        "total_storage_bytes": total_storage_bytes,
        "total_views": total_views,
        "processing_count": processing_count,
        "ready_count": ready_count,
        "error_count": error_count,
    }
