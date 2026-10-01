from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/iptv.db"
    # Global workers; keep moderate. Per-host is the main origin protection.
    max_concurrency: int = Field(20, ge=1)
    # Serial per host by default — one domain one in-flight test.
    max_host_concurrency: int = Field(1, ge=1)
    connect_timeout: float = Field(5, gt=0)
    read_timeout: float = Field(10, gt=0)
    ffprobe_timeout: float = Field(15, gt=0)
    # Separate, low FFprobe concurrency (full mode only).
    ffprobe_concurrency: int = Field(2, ge=1, le=16)
    # 1–2 segments for liveness; raise for finer speed samples.
    segment_test_count: int = Field(2, ge=1)
    test_interval_minutes: int = Field(30, ge=1)
    # Skip a source if its last test is newer than this many minutes (0 = off).
    min_test_interval_minutes: int = Field(30, ge=0, le=10080)
    # Periodic full (FFprobe) profile — independent of standard interval.
    full_test_enabled: bool = False
    full_test_interval_hours: int = Field(24, ge=1, le=168)
    min_score: float = Field(70, ge=0, le=100)
    min_stability: float = Field(0.90, ge=0, le=1)
    api_token: str = ""
    public_playlist: bool = False
    history_retention_days: int = Field(30, ge=1)
    network_retries: int = Field(1, ge=0, le=3)
    max_playlist_bytes: int = Field(2 * 1024 * 1024, ge=65536, le=20 * 1024 * 1024)
    max_segment_bytes: int = Field(32 * 1024 * 1024, ge=1024 * 1024, le=256 * 1024 * 1024)
    remote_playlist_max_failures: int = Field(3, ge=1, le=20)
    source_auto_delete_failures: int = Field(5, ge=1, le=100)
    source_auto_delete_days: int = Field(5, ge=1, le=365)
    # After 403/429 (and similar), pause that host before more tests.
    host_cooldown_seconds: int = Field(180, ge=0, le=3600)
    # Mild fixed UA when the source does not carry its own User-Agent.
    default_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
