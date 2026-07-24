from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class VideoOut(BaseModel):
    id: str
    mapping: str
    title: str
    status: str
    thumbnail: Optional[str] = None
    folder: Optional[str] = None
    views: int = 0
    created_at: str
    updated_at: str


class VideoDetailOut(VideoOut):
    qualities: Dict[str, str] = {}
    hls: Dict[str, Any] = {}
    master_playlist: Optional[str] = None
    preview_image: Optional[str] = None
    preview_video: Optional[str] = None
    thumbnails: List[str] = []
    seek_thumbnails: List[str] = []
    all_files: List[Dict[str, str]] = []
    telegram_posted_channels: List[str] = []


class PaginatedVideos(BaseModel):
    items: List[VideoOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class OverviewStats(BaseModel):
    total_videos: int
    total_storage_bytes: int
    total_views: int
    processing_count: int
    ready_count: int
    error_count: int


class ChannelIn(BaseModel):
    name: str
    channel_id: str
    interval_minutes: int = Field(description="0 = post now / manual, otherwise minutes between posts")
    post_quantity: int = 1
    active: bool = True


class ChannelOut(ChannelIn):
    id: str
    last_posted_at: Optional[str] = None


class BotSettingsIn(BaseModel):
    bot_token: Optional[str] = None


INTERVAL_PRESETS_MINUTES = {
    "now": 0,
    "15min": 15,
    "30min": 30,
    "1hour": 60,
    "2hours": 120,
    "6hours": 360,
    "12hours": 720,
    "24hours": 1440,
}
