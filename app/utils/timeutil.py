"""UTC-aware helpers for consistent API timestamps.

DB columns store naive UTC (historical). API responses always emit ISO-8601 with
a ``Z`` suffix so browsers convert to the viewer's local timezone correctly.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def utc_now() -> datetime:
    """Naive UTC now — compatible with existing DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def app_timezone() -> ZoneInfo:
    """Timezone from container ``TZ`` (default Asia/Shanghai, then UTC)."""
    name = (os.environ.get("TZ") or "Asia/Shanghai").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def to_iso(dt: datetime | None) -> str | None:
    """Serialize datetime for JSON: always UTC with trailing ``Z``."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Treat naive values as UTC (how this app stores timestamps).
        return dt.isoformat(timespec="seconds") + "Z"
    return (
        dt.astimezone(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
        + "Z"
    )
