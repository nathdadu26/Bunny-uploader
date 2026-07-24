import asyncio
import mimetypes
import boto3
from botocore.config import Config
from app.config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint_url,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _client


def _upload_sync(local_path: str, key: str) -> str:
    client = _get_client()
    content_type, _ = mimetypes.guess_type(local_path)
    extra_args = {"ContentType": content_type} if content_type else {}
    client.upload_file(local_path, settings.R2_BUCKET_NAME, key, ExtraArgs=extra_args)
    base = settings.R2_PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/{key}"


async def upload_file(local_path: str, key: str) -> str:
    """Uploads a single local file to R2 under `key` and returns its public URL."""
    return await asyncio.to_thread(_upload_sync, local_path, key)


def _delete_prefix_sync(prefix: str) -> None:
    client = _get_client()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.R2_BUCKET_NAME, Prefix=prefix):
        objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=settings.R2_BUCKET_NAME, Delete={"Objects": objects})


async def delete_prefix(prefix: str) -> None:
    """Deletes every object under a given key prefix (used when a video is deleted)."""
    await asyncio.to_thread(_delete_prefix_sync, prefix)
