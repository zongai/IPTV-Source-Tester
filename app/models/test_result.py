from datetime import datetime
from pydantic import BaseModel

class TestResult(BaseModel):
    id: int | None = None
    source_id: int
    tested_at: datetime
    dns_latency: float | None = None
    connect_latency: float | None = None
    ttfb: float | None = None
    http_status: int | None = None
    content_type: str | None = None
    playlist_valid: bool | None = None
    segment_valid: bool | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    bitrate: int | None = None
    download_speed: float | None = None
    min_speed: float | None = None
    max_speed: float | None = None
    startup_time: float | None = None
    stability: float | None = None
    failure_rate: float | None = None
    score: float | None = None
    error_type: str | None = None
    error_message: str | None = None
