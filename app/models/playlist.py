from pydantic import BaseModel, Field

class PlaylistEntry(BaseModel):
    name: str = ""
    url: str
    attributes: dict[str, str] = Field(default_factory=dict)
    unknown_attributes: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    raw_extinf: str | None = None
    group: str | None = None
    tvg_id: str | None = None
    tvg_name: str | None = None
    tvg_logo: str | None = None
    tvg_language: str | None = None
    tvg_country: str | None = None
