import os
import shutil
import tempfile
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List, Optional

from app.database import videos_collection
from app.core import bunny, naming
from app.core.pipeline import run_pipeline
from app.core.logs import log_event

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("")
async def upload_videos(
    files: List[UploadFile] = File(...),
    folder: Optional[str] = Form(None),
):
    """
    Accepts one or many video files in a single request (the dashboard's
    upload widget supports multi-select and drag-and-drop of a whole
    folder). Each file is:

      1. Validated as a video (images/audio are rejected).
      2. Renamed to TG-@atoz_links-VID_{timestamp}{ext} — the ORIGINAL
         filename is never stored anywhere.
      3. Registered + uploaded to Bunny Stream.
      4. Saved to MongoDB with status=PROCESSING (blank title, no
         thumbnail yet — the dashboard shows a black placeholder thumb).
      5. Handed off to a background task that waits for transcoding,
         downloads the zip, extracts it, uploads to R2, and flips the
         doc to status=READY once everything is stored.
    """
    if not files:
        raise HTTPException(400, "No files provided")

    results = []

    for upload_file in files:
        original_name = upload_file.filename or "video"
        ext = os.path.splitext(original_name)[1].lower() or ".mp4"

        if not naming.is_video_file(original_name):
            results.append({"file": original_name, "error": "Only video files are supported"})
            continue

        custom_filename = naming.generate_custom_filename(ext)
        mapping = naming.generate_mapping()

        # Save the incoming upload to a temp path so we can hand a real file
        # path to the Bunny upload call (streaming straight through works
        # too, but a temp file keeps memory usage predictable for large
        # multi-GB videos).
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
        os.close(tmp_fd)
        try:
            with open(tmp_path, "wb") as out:
                shutil.copyfileobj(upload_file.file, out)

            await log_event(f"Uploading '{custom_filename}' to Bunny Stream...", mapping=mapping)
            bunny_video = await bunny.create_video(title=custom_filename)
            bunny_video_id = bunny_video["guid"]
            await bunny.upload_video_file(bunny_video_id, tmp_path)
            await log_event(f"Upload to Bunny Stream complete (video id {bunny_video_id})", mapping=mapping)

            now_iso = datetime.now(timezone.utc).isoformat()
            doc = {
                "mapping": mapping,
                "bunny_video_id": bunny_video_id,
                "custom_filename": custom_filename,
                "title": "",
                "status": "PROCESSING",
                "thumbnail": None,
                "folder": folder,
                "views": 0,
                "telegram_posted_channels": [],
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            insert_result = await videos_collection.insert_one(doc)

            # Fire-and-forget background pipeline: poll -> zip -> unzip -> R2 -> DB
            import asyncio
            asyncio.create_task(
                run_pipeline(
                    mongo_id=insert_result.inserted_id,
                    bunny_video_id=bunny_video_id,
                    mapping=mapping,
                    display_title=custom_filename,
                )
            )

            results.append({
                "file": custom_filename,
                "mapping": mapping,
                "status": "PROCESSING",
            })
        except Exception as exc:  # noqa: BLE001
            # A failure here (bad Bunny credentials, network error, etc.)
            # used to bubble up as an unhandled 500 with nothing logged
            # anywhere. Now it's recorded in the realtime log feed and
            # reported back per-file so the rest of the batch still
            # uploads.
            await log_event(
                f"Upload failed for '{custom_filename}'",
                level="error", mapping=mapping, exc=exc,
            )
            results.append({"file": custom_filename, "error": str(exc)})
        finally:
            os.remove(tmp_path)

    return {"uploaded": results}
