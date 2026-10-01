import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import ChannelDB, SourceDB, TestResultDB
from app.scoring.quality import calculate_score

logger = logging.getLogger(__name__)

# Media fields produced only by FFprobe. Non-Full tests must not wipe them.
FFPROBE_MEDIA_FIELDS = (
    "width",
    "height",
    "video_codec",
    "audio_codec",
    "fps",
    "bitrate",
    "ffprobe_json",
)


def retain_ffprobe_media_fields(session: Session, source_id: int, result: dict) -> dict:
    """Preserve last FFprobe resolution until the next successful FFprobe run.

    Quick/Standard tests cannot measure width/height. Each test still writes a new
    TestResult row, and the UI/subscription use the latest validated row. Without
    carry-forward, a later Standard pass would clear resolution until Full runs again.
    """
    if not isinstance(result, dict):
        return result
    # This result already measured resolution (Full + FFprobe success) — keep as-is.
    if result.get("height") is not None:
        return result

    prev = session.scalar(
        select(TestResultDB)
        .where(TestResultDB.source_id == source_id, TestResultDB.height.is_not(None))
        .order_by(TestResultDB.tested_at.desc())
        .limit(1)
    )
    if prev is None:
        return result

    height_carried = False
    for field in FFPROBE_MEDIA_FIELDS:
        if result.get(field) is None:
            value = getattr(prev, field, None)
            if value is not None:
                result[field] = value
                if field == "height":
                    height_carried = True

    # Re-score Standard passes so retained resolution contributes to the 100-point formula.
    if height_carried and result.get("segment_valid") is True and result.get("score") is not None:
        stability = result.get("stability") or 0
        result["score"] = calculate_score(
            stability,
            stability,
            (result.get("ttfb") or 0) * 1000,
            result.get("download_speed"),
            result.get("height"),
            result.get("startup_time"),
        )
    return result


def _consecutive_validated_failures(session: Session, source_id: int):
    """Return (consecutive_failure_count, oldest_failure_time_in_streak).

    Only Standard/Full rows are considered (`segment_valid IS NOT NULL`).
    Quick connectivity checks leave segment_valid unset and do not count.
    """
    rows = list(
        session.scalars(
            select(TestResultDB)
            .where(
                TestResultDB.source_id == source_id,
                TestResultDB.segment_valid.is_not(None),
            )
            .order_by(TestResultDB.tested_at.desc())
            .limit(200)
        )
    )
    consecutive = 0
    streak_start = None
    for row in rows:
        if row.segment_valid is False:
            consecutive += 1
            streak_start = row.tested_at  # walks backward → ends at oldest failure
        else:
            break
    return consecutive, streak_start


def maybe_auto_delete_failed_source(session: Session, source_id: int) -> dict | None:
    """Delete a source when consecutive failures AND failure duration thresholds are met.

    Conditions (AND):
    1. consecutive validated failures >= SOURCE_AUTO_DELETE_FAILURES (default 5)
    2. failure streak age >= SOURCE_AUTO_DELETE_DAYS days (default 5)

    Deletes the source and its test results; removes the channel if it becomes empty.
    Returns a summary dict when deleted, otherwise None.
    """
    settings = get_settings()
    min_failures = settings.source_auto_delete_failures
    min_days = settings.source_auto_delete_days

    source = session.get(SourceDB, source_id)
    if source is None:
        return None

    consecutive, streak_start = _consecutive_validated_failures(session, source_id)
    if consecutive < min_failures or streak_start is None:
        return None

    age = datetime.utcnow() - streak_start
    if age < timedelta(days=min_days):
        return None

    channel_id = source.channel_id
    url = source.url
    session.execute(delete(TestResultDB).where(TestResultDB.source_id == source_id))
    session.delete(source)
    session.flush()

    remaining = session.scalar(
        select(SourceDB.id).where(SourceDB.channel_id == channel_id).limit(1)
    )
    channel_deleted = False
    if remaining is None:
        ch = session.get(ChannelDB, channel_id)
        if ch is not None:
            session.delete(ch)
            channel_deleted = True

    summary = {
        "deleted": True,
        "source_id": source_id,
        "channel_id": channel_id,
        "url": url,
        "consecutive_failures": consecutive,
        "failure_days": round(age.total_seconds() / 86400, 2),
        "channel_deleted": channel_deleted,
        "reason": (
            f"auto-deleted after {consecutive} consecutive failures "
            f"spanning {age.days}+ days "
            f"(thresholds: {min_failures} failures AND {min_days} days)"
        ),
    }
    logger.warning(
        "Source auto-deleted id=%s channel=%s consecutive=%s days=%.2f url=%s",
        source_id,
        channel_id,
        consecutive,
        age.total_seconds() / 86400,
        (url or "")[:120],
    )
    return summary


def _latest_validated_result(session: Session, source_id: int) -> TestResultDB | None:
    return session.scalars(
        select(TestResultDB)
        .where(
            TestResultDB.source_id == source_id,
            TestResultDB.segment_valid.is_not(None),
        )
        .order_by(TestResultDB.tested_at.desc())
        .limit(1)
    ).first()


def list_failed_source_ids(session: Session) -> list[int]:
    """Sources considered invalid: latest validated result failed, or status marks failure."""
    ids: list[int] = []
    for src in session.scalars(select(SourceDB)).all():
        if src.status in {"temporarily_failed", "inactive", "failed"}:
            ids.append(src.id)
            continue
        latest = _latest_validated_result(session, src.id)
        if latest is not None and latest.segment_valid is False:
            ids.append(src.id)
    return ids


def delete_source_cascade(session: Session, source_id: int) -> dict | None:
    """Delete one source, its test results, and the channel if empty."""
    source = session.get(SourceDB, source_id)
    if source is None:
        return None
    channel_id = source.channel_id
    url = source.url
    session.execute(delete(TestResultDB).where(TestResultDB.source_id == source_id))
    session.delete(source)
    session.flush()
    remaining = session.scalar(
        select(SourceDB.id).where(SourceDB.channel_id == channel_id).limit(1)
    )
    channel_deleted = False
    if remaining is None:
        ch = session.get(ChannelDB, channel_id)
        if ch is not None:
            session.delete(ch)
            channel_deleted = True
    return {
        "source_id": source_id,
        "channel_id": channel_id,
        "url": url,
        "channel_deleted": channel_deleted,
    }


def purge_failed_sources(session: Session) -> dict:
    """One-shot delete of all currently failed/invalid sources.

    A source is purged when:
    - status is temporarily_failed / inactive / failed, or
    - the latest validated test result has segment_valid == False.

    Untested sources (no validated result) are kept.
    """
    target_ids = list_failed_source_ids(session)
    deleted = []
    channels_removed = 0
    for sid in target_ids:
        info = delete_source_cascade(session, sid)
        if info:
            deleted.append(info)
            if info.get("channel_deleted"):
                channels_removed += 1
    logger.warning(
        "Purged %s failed sources (%s empty channels removed)",
        len(deleted),
        channels_removed,
    )
    return {
        "deleted_sources": len(deleted),
        "deleted_channels": channels_removed,
        "source_ids": [x["source_id"] for x in deleted],
    }
