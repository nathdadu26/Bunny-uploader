"""
Koyeb's free tier puts a web service to sleep after a period of no
incoming HTTP traffic, and it wakes back up on the next request (with a
cold-start delay). To keep the service warm, this module pings the
service's own public health-check URL on a fixed interval from inside
the running process itself — no external cron/uptime service required.

Configure via .env:
  PUBLIC_URL=https://your-app-xxxx.koyeb.app
  SELF_PING_INTERVAL_MINUTES=4     # keep well under Koyeb's idle timeout

If PUBLIC_URL is not set, self-pinging is simply skipped (e.g. when
running locally) — nothing else in the app depends on it.
"""

import logging
import httpx

from app.config import settings

logger = logging.getLogger("keepalive")


async def ping_self():
    if not settings.PUBLIC_URL:
        return
    url = settings.PUBLIC_URL.rstrip("/") + "/api/health"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            logger.info("Self-ping %s -> %s", url, resp.status_code)
    except Exception:  # noqa: BLE001
        logger.exception("Self-ping failed")


def register_keepalive_job(scheduler):
    if not settings.PUBLIC_URL:
        logger.info("PUBLIC_URL not set — skipping keepalive self-ping job")
        return
    scheduler.add_job(
        ping_self,
        "interval",
        minutes=settings.SELF_PING_INTERVAL_MINUTES,
        id="self_ping_keepalive",
        replace_existing=True,
    )
