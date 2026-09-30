from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.database import Base

class ChannelDB(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    tvg_id: Mapped[str | None] = mapped_column(String(255))
    tvg_logo: Mapped[str | None] = mapped_column(Text)
    group_name: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(64))
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sources: Mapped[list["SourceDB"]] = relationship(back_populates="channel")

class SourceDB(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text, index=True)
    source_playlist: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    referer: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str | None] = mapped_column(Text)
    cookie: Mapped[str | None] = mapped_column(Text)
    authorization: Mapped[str | None] = mapped_column(Text)
    protocol: Mapped[str] = mapped_column(String(32))
    host: Mapped[str | None] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    channel: Mapped[ChannelDB] = relationship(back_populates="sources")

Index("ix_sources_url_headers", SourceDB.normalized_url, SourceDB.user_agent, SourceDB.referer)

class TestResultDB(Base):
    __tablename__ = "test_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    tested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    dns_latency: Mapped[float | None] = mapped_column(Float)
    ttfb: Mapped[float | None] = mapped_column(Float)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(255))
    playlist_valid: Mapped[bool | None] = mapped_column(Boolean)
    segment_valid: Mapped[bool | None] = mapped_column(Boolean)
    video_codec: Mapped[str | None] = mapped_column(String(64))
    audio_codec: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    bitrate: Mapped[int | None] = mapped_column(Integer)
    download_speed: Mapped[float | None] = mapped_column(Float)
    min_speed: Mapped[float | None] = mapped_column(Float)
    max_speed: Mapped[float | None] = mapped_column(Float)
    startup_time: Mapped[float | None] = mapped_column(Float)
    stability: Mapped[float | None] = mapped_column(Float)
    failure_rate: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    error_type: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    ffprobe_json: Mapped[str | None] = mapped_column(Text)

class SchedulerConfigDB(Base):
    __tablename__ = "scheduler_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    test_mode: Mapped[str] = mapped_column(String(16), default="standard")
    source_scope: Mapped[str] = mapped_column(String(16), default="enabled")
    stale_hours: Mapped[int] = mapped_column(Integer, default=24)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=20)
    max_host_concurrency: Mapped[int] = mapped_column(Integer, default=5)
    connect_timeout: Mapped[int] = mapped_column(Integer, default=5)
    read_timeout: Mapped[int] = mapped_column(Integer, default=10)
    segment_test_count: Mapped[int] = mapped_column(Integer, default=3)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_status: Mapped[str] = mapped_column(String(32), default="never")
    last_tested: Mapped[int] = mapped_column(Integer, default=0)
    last_failed: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SchedulerRunDB(Base):
    __tablename__ = "scheduler_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    trigger: Mapped[str] = mapped_column(String(16), default="scheduled", index=True)
    test_mode: Mapped[str] = mapped_column(String(16))
    source_scope: Mapped[str] = mapped_column(String(16))
    total: Mapped[int] = mapped_column(Integer, default=0)
    tested: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)


class RemotePlaylistDB(Base):
    __tablename__ = "remote_playlists"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=360)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_status: Mapped[str] = mapped_column(String(32), default="never")
    last_added: Mapped[int] = mapped_column(Integer, default=0)
    last_skipped: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    auto_deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
