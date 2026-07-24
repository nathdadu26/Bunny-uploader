import asyncio
import os
import shutil
from datetime import datetime, timezone

from app.config import settings
from app.database import videos_collection
from app.core import bunny, zip_processor

POLL_INTERVAL_SECONDS = 10
MAX_POLL_ATTEMPTS = 6 * 60  # up to ~1 hour of polling


async def _set_status(mongo_id, **fields):
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    await videos_collection.update_one({"_id": mongo_id}, {"$set": fields})


async def run_pipeline(mongo_id, bunny_video_id: str, mapping: str, display_title: str):
    """
    Full lifecycle for one uploaded video, run as a background task right
    after the raw file has been handed off to Bunny Stream:

      1. Poll Bunny until transcoding is Finished (status 4).
      2. Download the finished output zip.
      3. Unzip it.
      4. Upload every extracted file to Cloudflare R2.
      5. Save every resulting link into MongoDB and flip status -> READY.

    Any failure along the way marks the video as ERROR with a reason,
    rather than leaving it stuck on PROCESSING forever.
    """
    work_dir = os.path.join(settings.TEMP_WORK_DIR, mapping)
    zip_path = os.path.join(work_dir, "output.zip")
    extract_dir = os.path.join(work_dir, "extracted")

    try:
        # 1. Wait for Bunny to finish transcoding
        for _ in range(MAX_POLL_ATTEMPTS):
            info = await bunny.get_video(bunny_video_id)
            status = info.get("status")

            if status in bunny.ERROR_STATUSES:
                await _set_status(
                    mongo_id,
                    status="ERROR",
                    error_reason=f"Bunny transcoding failed with status {status}",
                )
                return

            if status == bunny.STATUS_FINISHED:
                break

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        else:
            await _set_status(mongo_id, status="ERROR", error_reason="Transcoding timed out")
            return

        # 2. Download the finished output zip
        os.makedirs(work_dir, exist_ok=True)
        await bunny.download_output_zip(bunny_video_id, zip_path)

        # 3. Unzip
        zip_processor.extract_zip(zip_path, extract_dir)

        # 4. Upload every file inside to R2 + categorize links
        links = await zip_processor.process_and_upload(extract_dir, mapping)

        # 5. Save everything to MongoDB, video is now ready
        await _set_status(
            mongo_id,
            status="READY",
            title=display_title,
            thumbnail=links["thumbnail"],
            thumbnails=links["thumbnails"],
            preview_image=links["preview_image"],
            preview_video=links["preview_video"],
            master_playlist=links["master_playlist"],
            qualities=links["qualities"],
            hls=links["hls"],
            seek_thumbnails=links["seek_thumbnails"],
            all_files=links["all_files"],
        )

    except Exception as exc:  # noqa: BLE001
        await _set_status(mongo_id, status="ERROR", error_reason=str(exc))

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
