import httpx
from app.config import settings
from app.database import settings_collection

BLACK_PLACEHOLDER_THUMB = None  # while PROCESSING we simply show no/blank thumbnail in the UI


async def get_bot_token() -> str:
    doc = await settings_collection.find_one({"_id": "bot"})
    if doc and doc.get("bot_token"):
        return doc["bot_token"]
    return settings.TELEGRAM_BOT_TOKEN


def build_streaming_link(mapping: str) -> str:
    """Only builds the caption link — this project never hosts a streaming page itself."""
    domain = settings.STREAMING_DOMAIN.rstrip("/")
    return f"{domain}/ad/{mapping}"


async def post_video_to_channel(channel_id: str, thumbnail_url: str, title: str, mapping: str) -> dict:
    token = await get_bot_token()
    if not token:
        raise RuntimeError("Telegram bot token is not configured")

    link = build_streaming_link(mapping)
    caption = f"{title}\n\n{link}"

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {
        "chat_id": channel_id,
        "photo": thumbnail_url,
        "caption": caption,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


async def verify_bot_is_admin(channel_id: str) -> dict:
    """Calls getChatMember for the bot itself to help the settings page confirm admin status."""
    token = await get_bot_token()
    me_url = f"https://api.telegram.org/bot{token}/getMe"
    async with httpx.AsyncClient(timeout=15) as client:
        me_resp = await client.get(me_url)
        me_resp.raise_for_status()
        bot_id = me_resp.json()["result"]["id"]

        member_url = f"https://api.telegram.org/bot{token}/getChatMember"
        member_resp = await client.get(member_url, params={"chat_id": channel_id, "user_id": bot_id})
        member_resp.raise_for_status()
        return member_resp.json()
