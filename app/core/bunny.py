"""
Thin async wrapper around the Bunny Stream API.

Docs referenced (Bunny Stream video library API):
- Create video:  POST {base}/library/{libraryId}/videos           (json body: {"title": ...})
- Upload video:  PUT  {base}/library/{libraryId}/videos/{videoId}  (raw binary body)
- Get video:     GET  {base}/library/{libraryId}/videos/{videoId}
- Delete video:  DELETE {base}/library/{libraryId}/videos/{videoId}

Bunny Stream's `status` field on the video object is an integer:
  0 = Created, 1 = Uploaded, 2 = Processing, 3 = Transcoding,
  4 = Finished, 5 = Error, 6 = UploadFailed
We poll until status == 4 (Finished) or an error status is hit.

The finished output (all qualities of mp4, HLS folders, master.m3u8,
thumbnails, preview, seek sprites, etc.) is downloaded as a single zip
straight from the storage zone backing the library, using the exact
URL format requested:

    https://storage.bunnycdn.com/{BUNNY_STORAGE_ZONE_NAME}/{videoId}/?accessKey={BUNNY_STORAGE_PASSWORD}&download
"""

import httpx
from app.config import settings

STATUS_CREATED = 0
STATUS_UPLOADED = 1
STATUS_PROCESSING = 2
STATUS_TRANSCODING = 3
STATUS_FINISHED = 4
STATUS_ERROR = 5
STATUS_UPLOAD_FAILED = 6

ERROR_STATUSES = {STATUS_ERROR, STATUS_UPLOAD_FAILED}


def _headers() -> dict:
    return {
        "AccessKey": settings.BUNNY_STREAM_API_KEY,
        "accept": "application/json",
    }


async def create_video(title: str) -> dict:
    """Creates a video object in the library and returns Bunny's JSON (contains 'guid')."""
    url = f"{settings.BUNNY_STREAM_BASE_URL}/library/{settings.BUNNY_LIBRARY_ID}/videos"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers={**_headers(), "content-type": "application/*+json"},
                                  json={"title": title})
        resp.raise_for_status()
        return resp.json()


async def upload_video_file(video_id: str, file_path: str) -> None:
    """Uploads the raw video bytes for a previously-created video object."""
    url = f"{settings.BUNNY_STREAM_BASE_URL}/library/{settings.BUNNY_LIBRARY_ID}/videos/{video_id}"
    with open(file_path, "rb") as f:
        data = f.read()
    async with httpx.AsyncClient(timeout=None) as client:
        resp = await client.put(url, headers={**_headers(), "content-type": "application/octet-stream"},
                                 content=data)
        resp.raise_for_status()


async def get_video(video_id: str) -> dict:
    url = f"{settings.BUNNY_STREAM_BASE_URL}/library/{settings.BUNNY_LIBRARY_ID}/videos/{video_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers())
        resp.raise_for_status()
        return resp.json()


async def delete_video(video_id: str) -> None:
    url = f"{settings.BUNNY_STREAM_BASE_URL}/library/{settings.BUNNY_LIBRARY_ID}/videos/{video_id}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(url, headers=_headers())
        resp.raise_for_status()


def build_zip_download_url(video_id: str) -> str:
    zone = settings.BUNNY_STORAGE_ZONE_NAME
    key = settings.BUNNY_STORAGE_PASSWORD
    host = settings.BUNNY_STORAGE_PULLZONE_HOST
    return f"https://{host}/{zone}/{video_id}/?accessKey={key}&download"


async def download_output_zip(video_id: str, dest_path: str) -> str:
    """Streams the finished video's full output zip to dest_path on disk."""
    url = build_zip_download_url(video_id)
    headers = {"AccessKey": settings.BUNNY_STORAGE_PASSWORD}
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise RuntimeError(
                    f"Bunny storage returned {resp.status_code} for {url}: {body[:300].decode(errors='replace')}"
                )
            with open(dest_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
    return dest_path
