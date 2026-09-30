from datetime import datetime
from pydantic import BaseModel, Field

class Channel(BaseModel):
    id: str
    canonical_name: str
    display_name: str
    tvg_id: str | None = None
    tvg_logo: str | None = None
    group: str | None = None
    language: str | None = None
    country: str | None = None
    aliases: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
