from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MongoDB
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "bunny_r2_tg"

    # Bunny Stream
    BUNNY_LIBRARY_ID: str = ""
    BUNNY_STREAM_API_KEY: str = ""
    BUNNY_STREAM_BASE_URL: str = "https://video.bunnycdn.com"

    # Bunny Storage (zip download)
    BUNNY_STORAGE_ZONE_NAME: str = ""
    BUNNY_STORAGE_PASSWORD: str = ""
    BUNNY_STORAGE_PULLZONE_HOST: str = "storage.bunnycdn.com"

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "videos"
    R2_PUBLIC_BASE_URL: str = ""

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""

    # Streaming domain used only to build the caption link (no page is hosted here)
    STREAMING_DOMAIN: str = "https://example.com"

    # Misc
    TEMP_WORK_DIR: str = "./tmp_processing"
    FILES_PAGE_SIZE: int = 25
    SESSION_SECRET: str = "change-this-secret"
    DASHBOARD_USERNAME: str = "admin"
    DASHBOARD_PASSWORD: str = "change-this-password"

    # Deployment / keepalive (Koyeb free tier sleeps idle services)
    PUBLIC_URL: str = ""              # e.g. https://your-app-xxxx.koyeb.app
    SELF_PING_INTERVAL_MINUTES: int = 4
    PORT: int = 8000

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"


settings = Settings()
