from datetime import datetime
from pydantic import BaseModel

class Source(BaseModel):
    id: int | None = None
    channel_id: str
    url: str
    normalized_url: str
    source_playlist: str | None = None
    user_agent: str | None = None
    referer: str | None = None
    origin: str | None = None
    cookie: str | None = None
    authorization: str | None = None
    protocol: str
    host: str | None = None
    port: int | None = None
    enabled: bool = True
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None
