"""
Handles a downloaded Bunny Stream output zip:

1. Extracts it to a temp folder.
2. Walks every file inside (root-level files + nested HLS/seek folders).
3. Uploads every single file to R2, preserving the relative folder layout
   under `videos/{mapping}/...`.
4. While uploading, buckets each file into a category so the DB can store
   clean, direct links for: thumbnails, per-quality mp4s, HLS folders,
   master.m3u8, per-quality playlist.m3u8, preview video/image, and seek
   sprite folder — plus a full flat list of everything as a safety net so
   nothing from the zip is ever lost even if Bunny changes its internal
   folder naming.
"""

import os
import re
import zipfile
from app.core import r2

MP4_QUALITY_RE = re.compile(r"^(\d{3,4})p\.mp4$", re.IGNORECASE)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def extract_zip(zip_path: str, extract_dir: str) -> str:
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    return extract_dir


def _relative_parts(root: str, full_path: str):
    rel = os.path.relpath(full_path, root)
    return rel.replace(os.sep, "/")


async def process_and_upload(extract_dir: str, mapping: str) -> dict:
    """
    Walks the extracted folder, uploads every file to R2 under
    videos/{mapping}/{relative_path}, and returns a structured links dict:

    {
      "thumbnail": str | None,           # primary thumbnail
      "thumbnails": [str, ...],          # every thumbnail found
      "preview_image": str | None,
      "preview_video": str | None,       # preview.webp / preview.mp4 (hover preview)
      "master_playlist": str | None,     # master.m3u8 / playlist.m3u8 at root
      "qualities": {"240p": url, "360p": url, ...},   # per-quality mp4 fallback files
      "hls": {
          "240p": {"playlist": url, "segments": [url, ...]},
          ...
      },
      "seek_thumbnails": [url, ...],
      "all_files": [{"path": rel_path, "url": url}, ...]  # everything, no exceptions
    }
    """
    links = {
        "thumbnail": None,
        "thumbnails": [],
        "preview_image": None,
        "preview_video": None,
        "master_playlist": None,
        "qualities": {},
        "hls": {},
        "seek_thumbnails": [],
        "all_files": [],
    }

    for current_root, _dirs, files in os.walk(extract_dir):
        for fname in files:
            full_path = os.path.join(current_root, fname)
            rel_path = _relative_parts(extract_dir, full_path)
            key = f"videos/{mapping}/{rel_path}"
            url = await r2.upload_file(full_path, key)
            size_bytes = os.path.getsize(full_path)

            links["all_files"].append({"path": rel_path, "url": url, "size": size_bytes})

            lower = fname.lower()
            parts = rel_path.split("/")
            ext = os.path.splitext(fname)[1].lower()

            is_in_seek_folder = "seek" in [p.lower() for p in parts[:-1]]

            if is_in_seek_folder and ext in IMAGE_EXTS:
                links["seek_thumbnails"].append(url)
                continue

            if "thumb" in lower and ext in IMAGE_EXTS:
                links["thumbnails"].append(url)
                if links["thumbnail"] is None:
                    links["thumbnail"] = url
                continue

            if lower.startswith("preview") and ext in IMAGE_EXTS:
                links["preview_image"] = url
                continue

            if lower.startswith("preview") and ext in {".webp", ".mp4", ".gif"}:
                links["preview_video"] = url
                continue

            if len(parts) == 1 and lower in {"master.m3u8", "playlist.m3u8", "index.m3u8"}:
                links["master_playlist"] = url
                continue

            if len(parts) == 1:
                m = MP4_QUALITY_RE.match(fname)
                if m:
                    quality = f"{m.group(1)}p"
                    links["qualities"][quality] = url
                    continue

            if ext in {".m3u8"} and len(parts) > 1:
                quality_folder = parts[-2]
                links["hls"].setdefault(quality_folder, {"playlist": None, "segments": []})
                links["hls"][quality_folder]["playlist"] = url
                continue

            if ext in {".ts", ".m4s"} and len(parts) > 1:
                quality_folder = parts[-2]
                links["hls"].setdefault(quality_folder, {"playlist": None, "segments": []})
                links["hls"][quality_folder]["segments"].append(url)
                continue

            # Anything unrecognized still lives safely in all_files above.

    if links["thumbnails"] and links["thumbnail"] is None:
        links["thumbnail"] = links["thumbnails"][0]

    return links
