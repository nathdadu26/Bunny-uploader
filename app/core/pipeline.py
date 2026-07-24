import asyncio
import os
import shutil
from datetime import datetime, timezone

from app.config import settings
from app.database import videos_collection
from app.core import bunny, zip_processor
from app.core.logs import log_event

POLL_INTERVAL_SECONDS = 10
MAX_POLL_ATTEMPTS = 6 * 60  # up to ~1 hour of polling

STATUS_LABELS = {
    bunny.STATUS_CREATED: "Created",
    bunny.STATUS_UPLOADED: "Uploaded",
    bunny.STATUS_PROCESSING: "Processing",
    bunny.STATUS_TRANSCODING: "Transcoding",
    bunny.STATUS_FINISHED: "Finished",
    bunny.STATUS_ERROR: "Error",
    bunny.STATUS_UPLOAD_FAILED: "UploadFailed",
}


async def _set_status(mongo_id, **fields):
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    await videos_collection.update_one({"_id": mongo_id}, {"$set": fields})


async def _fail(mongo_id, mapping: str, stage: str, message: str, exc: Exception | None = None):
    reason = f"[{stage}] {message}"
    await log_event(f"Failed at stage '{stage}': {message}", level="error", mapping=mapping, exc=exc)
    await _set_status(mongo_id, status="ERROR", error_reason=reason, error_stage=stage)


async def run_pipeline(mongo_id, bunny_video_id: str, mapping: str, display_title: str):
    """
    Full lifecycle for one uploaded video, run as a background task right
    after the raw file has been handed off to Bunny Stream:

      1. Poll Bunny until transcoding is Finished (status 4).
      2. Download the finished output zip.
      3. Unzip it.
      4. Upload every extracted file to Cloudflare R2.
      5. Save every resulting link into MongoDB and flip status -> READY.

    Every stage is wrapped separately so that when something fails, the
    video is marked ERROR with exactly which stage failed and the real
    exception message -- both in the server logs and in the `logs`
    collection the dashboard terminal streams from.
    """
    work_dir = os.path.join(settings.TEMP_WORK_DIR, mapping)
    zip_path = os.path.join(work_dir, "output.zip")
    extract_dir = os.path.join(work_dir, "extracted")

    await log_event(f"Pipeline started for '{display_title}'", mapping=mapping)

    # ---------------- Stage 1: wait for Bunny transcoding ----------------
    try:
        last_status = None
        for attempt in range(MAX_POLL_ATTEMPTS):
            info = await bunny.get_video(bunny_video_id)
            status = info.get("status")

            if status != last_status:
                label = STATUS_LABELS.get(status, str(status))
                await log_event(f"Bunny status: {label}", mapping=mapping)
                last_status = status

            if status in bunny.ERROR_STATUSES:
                await _fail(
                    mongo_id, mapping, "bunny_transcoding",
                    f"Bunny reported status {status} ({STATUS_LABELS.get(status, 'unknown')}). "
                    f"Check the video's encode/error details in the Bunny Stream dashboard.",
                )
                return

            if status == bunny.STATUS_FINISHED:
                break

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        else:
            await _fail(mongo_id, mapping, "bunny_transcoding", "Timed out waiting for transcoding to finish")
            return
    except Exception as exc:  # noqa: BLE001
        await _fail(mongo_id, mapping, "bunny_transcoding", "Error while polling Bunny Stream for status", exc)
        return

    # ---------------- Stage 2: download the output zip ----------------
    try:
        await log_event("Downloading output zip from Bunny storage...", mapping=mapping)
        os.makedirs(work_dir, exist_ok=True)
        await bunny.download_output_zip(bunny_video_id, zip_path)
        zip_size = os.path.getsize(zip_path)
        await log_event(f"Zip downloaded ({zip_size / (1024*1024):.1f} MB)", mapping=mapping)
    except Exception as exc:  # noqa: BLE001
        await _fail(
            mongo_id, mapping, "download_zip",
            "Could not download the output zip. Check BUNNY_STORAGE_ZONE_NAME / "
            "BUNNY_STORAGE_PASSWORD and that the storage zone is the one attached to this library",
            exc,
        )
        shutil.rmtree(work_dir, ignore_errors=True)
        return

    # ---------------- Stage 3: unzip ----------------
    try:
        await log_event("Unzipping...", mapping=mapping)
        zip_processor.extract_zip(zip_path, extract_dir)
        await log_event("Unzip complete", mapping=mapping)
    except Exception as exc:  # noqa: BLE001
        await _fail(mongo_id, mapping, "unzip", "Failed to extract the downloaded zip (it may be corrupt or empty)", exc)
        shutil.rmtree(work_dir, ignore_errors=True)
        return

    # ---------------- Stage 4: upload everything to R2 ----------------
    try:
        await log_event("Uploading extracted files to Cloudflare R2...", mapping=mapping)
        links = await zip_processor.process_and_upload(extract_dir, mapping)
        await log_event(f"Uploaded {len(links['all_files'])} file(s) to R2", mapping=mapping)
    except Exception as exc:  # noqa: BLE001
        await _fail(
            mongo_id, mapping, "upload_r2",
            "Failed while uploading extracted files to R2. Check R2_ACCOUNT_ID / "
            "R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_BUCKET_NAME",
            exc,
        )
        shutil.rmtree(work_dir, ignore_errors=True)
        return

    # ---------------- Stage 5: delete from Bunny Stream (now safe on R2) ----------------
    try:
        await log_event("Deleting video from Bunny Stream (already safe on R2)...", mapping=mapping)
        await bunny.delete_video(bunny_video_id)
        await log_event("Deleted from Bunny Stream", mapping=mapping)
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: the video is already fully saved to R2 + Mongo, so we
        # just warn instead of marking the whole pipeline as ERROR.
        await log_event(
            "Could not delete video from Bunny Stream (it will remain there, but R2/DB are already complete)",
            level="warn", mapping=mapping, exc=exc,
        )

    # ---------------- Stage 6: save to MongoDB, mark READY ----------------
    try:
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
            error_reason=None,
            error_stage=None,
        )
        await log_event(f"Video ready -- {display_title}", level="success", mapping=mapping)
    except Exception as exc:  # noqa: BLE001
        await _fail(mongo_id, mapping, "save_db", "Failed to save the final links to MongoDB", exc)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
