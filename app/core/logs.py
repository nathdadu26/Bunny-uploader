"""
Every meaningful step of the upload -> Bunny -> R2 -> Mongo -> Telegram
pipeline calls `log_event(...)` here. Each call does two things:

1. Writes to the normal Python logger, so it still shows up in
   `docker logs` / Koyeb's log viewer exactly like before.
2. Inserts a row into the capped `logs` Mongo collection, which the
   dashboard's Overview page polls to render a live terminal — so errors
   (with the stage they happened at + the real exception message) are
   visible in the UI even when nobody is tailing server logs.
"""

import logging
import traceback
from datetime import datetime, timezone

from app.database import logs_collection

logger = logging.getLogger("pipeline")


async def log_event(message: str, level: str = "info", mapping: str | None = None, exc: Exception | None = None):
    """
    level: "info" | "success" | "warn" | "error"
    mapping: the video's mapping slug, if this event is about a specific video
    exc: pass the caught exception to also store its traceback for debugging
    """
    full_message = message
    if exc is not None:
        full_message = f"{message}: {exc}"

    log_fn = {
        "error": logger.error,
        "warn": logger.warning,
    }.get(level, logger.info)
    log_fn("[%s] %s", mapping or "-", full_message)

    doc = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "mapping": mapping,
        "message": full_message,
        "traceback": traceback.format_exc() if exc is not None else None,
    }
    try:
        await logs_collection.insert_one(doc)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to write to logs collection")
