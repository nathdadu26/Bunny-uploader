import random
import string
from datetime import datetime


def generate_custom_filename(extension: str) -> str:
    """
    Builds: TG-@atoz_links-VID_{DDMMYYYYHHMMSS}{extension}
    The original uploaded filename is intentionally discarded and never stored.
    """
    now = datetime.utcnow()
    stamp = now.strftime("%d%m%Y%H%M%S")
    ext = extension if extension.startswith(".") else f".{extension}"
    return f"TG-@atoz_links-VID_{stamp}{ext}"


def generate_mapping(length: int = 12) -> str:
    """Short random slug used to build the public streaming link: STREAMING_DOMAIN/ad/{mapping}"""
    alphabet = string.ascii_lowercase + string.digits + "_"
    return "".join(random.choices(alphabet, k=length))


ALLOWED_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".flv", ".wmv", ".ts", ".3gp",
}


def is_video_file(filename: str) -> bool:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_VIDEO_EXTENSIONS
