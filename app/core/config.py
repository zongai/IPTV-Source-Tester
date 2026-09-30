from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/iptv.db"
    max_concurrency: int = Field(100, ge=1)
    max_host_concurrency: int = Field(5, ge=1)
    connect_timeout: float = Field(5, gt=0)
    read_timeout: float = Field(10, gt=0)
    ffprobe_timeout: float = Field(15, gt=0)
    segment_test_count: int = Field(3, ge=1)
    test_interval_minutes: int = Field(30, ge=1)
    min_score: float = Field(70, ge=0, le=100)
    min_stability: float = Field(0.90, ge=0, le=1)
    api_token: str = ""
    public_playlist: bool = False
    history_retention_days: int = Field(30, ge=1)
    network_retries: int = Field(1, ge=0, le=3)
    max_playlist_bytes: int = Field(2 * 1024 * 1024, ge=65536, le=20 * 1024 * 1024)
    max_segment_bytes: int = Field(32 * 1024 * 1024, ge=1024 * 1024, le=256 * 1024 * 1024)
    remote_playlist_max_failures: int = Field(3, ge=1, le=20)

@lru_cache
def get_settings() -> Settings:
    return Settings()
