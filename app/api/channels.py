from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.auth import require_admin
from app.database.database import SessionLocal
from app.database.models import ChannelDB, SourceDB, TestResultDB
from app.matcher.channel_matcher import channel_sort_key

router = APIRouter()


def _latest_validated_subquery():
    """One row per source: the newest result that has segment_valid set."""
    ranked = (
        select(
            TestResultDB.id.label("result_id"),
            TestResultDB.source_id.label("source_id"),
            func.row_number()
            .over(
                partition_by=TestResultDB.source_id,
                order_by=TestResultDB.tested_at.desc(),
            )
            .label("rn"),
        )
        .where(TestResultDB.segment_valid.is_not(None))
        .subquery()
    )
    return ranked


def _latest(session, source_id, validated_only=False):
    stmt = select(TestResultDB).where(TestResultDB.source_id == source_id)
    if validated_only:
        stmt = stmt.where(TestResultDB.segment_valid.is_not(None))
    return session.scalars(stmt.order_by(TestResultDB.tested_at.desc()).limit(1)).first()


@router.get("/channels", dependencies=[Depends(require_admin)])
def channels(
    q: str | None = Query(None, description="Filter by channel name"),
    status: str | None = Query(None, description="pass|fail|untested"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Return channel rows with the latest validated test result per source.

    Uses a single window-function query instead of per-source lookups.
    Supports optional name filter, status filter, and pagination.
    """
    with SessionLocal() as s:
        ranked = _latest_validated_subquery()
        # All sources joined to channels; left-join latest validated result.
        stmt = (
            select(ChannelDB, SourceDB, TestResultDB)
            .join(SourceDB, SourceDB.channel_id == ChannelDB.id)
            .outerjoin(ranked, (ranked.c.source_id == SourceDB.id) & (ranked.c.rn == 1))
            .outerjoin(TestResultDB, TestResultDB.id == ranked.c.result_id)
        )
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                ChannelDB.display_name.ilike(like) | ChannelDB.id.ilike(like)
            )

        rows = list(s.execute(stmt))

        # Group by channel while building flat result list for the UI table.
        by_channel: dict[str, dict] = {}
        for c, x, r in rows:
            item = {
                "id": x.id,
                "url": x.url,
                "status": x.status,
                "enabled": x.enabled,
                "score": r.score if r else None,
                "height": r.height if r else None,
                "speed": r.download_speed if r else None,
                "ttfb": r.ttfb if r else None,
                "segment_valid": r.segment_valid if r else None,
                "error_type": r.error_type if r else None,
                # Keep messages short in the list payload.
                "error_message": (r.error_message[:200] if r and r.error_message else None),
                "tested_at": r.tested_at.isoformat() if r and r.tested_at else None,
            }
            if status == "pass" and item["segment_valid"] is not True:
                continue
            if status == "fail" and item["segment_valid"] is not False:
                continue
            if status == "untested" and item["segment_valid"] is not None:
                continue

            bucket = by_channel.get(c.id)
            if bucket is None:
                bucket = {
                    "id": c.id,
                    "name": c.display_name,
                    "sources": 0,
                    "results": [],
                }
                by_channel[c.id] = bucket
            bucket["results"].append(item)
            bucket["sources"] = len(bucket["results"])

        out = list(by_channel.values())
        out.sort(key=lambda c: channel_sort_key(c["name"] or ""))

        # Flatten for total count, then paginate at channel level.
        total_channels = len(out)
        page = out[offset : offset + limit]
        total_results = sum(len(c["results"]) for c in out)
        page_results = sum(len(c["results"]) for c in page)

        return {
            "items": page,
            "total_channels": total_channels,
            "total_results": total_results,
            "page_results": page_results,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total_channels,
        }


@router.get("/channels/{channel_id}", dependencies=[Depends(require_admin)])
def channel(channel_id):
    with SessionLocal() as s:
        c = s.get(ChannelDB, channel_id)
        return (
            {
                "id": c.id,
                "name": c.display_name,
                "aliases": c.aliases_json,
                "source_count": len(c.sources),
            }
            if c
            else {"error": "not_found"}
        )


@router.get("/channels/{channel_id}/sources", dependencies=[Depends(require_admin)])
def channel_sources(channel_id):
    with SessionLocal() as s:
        ranked = _latest_validated_subquery()
        stmt = (
            select(SourceDB, TestResultDB)
            .where(SourceDB.channel_id == channel_id)
            .outerjoin(ranked, (ranked.c.source_id == SourceDB.id) & (ranked.c.rn == 1))
            .outerjoin(TestResultDB, TestResultDB.id == ranked.c.result_id)
        )
        out = []
        for x, r in s.execute(stmt):
            out.append(
                {
                    "id": x.id,
                    "url": x.url,
                    "status": x.status,
                    "score": r.score if r else None,
                    "resolution": r.height if r else None,
                    "bitrate": r.bitrate if r else None,
                    "speed": r.download_speed if r else None,
                    "latency": r.ttfb * 1000 if r and r.ttfb else None,
                    "segment_valid": r.segment_valid if r else None,
                    "error_type": r.error_type if r else None,
                    "error_message": r.error_message if r else None,
                    "tested_at": r.tested_at.isoformat() if r and r.tested_at else None,
                }
            )
        return out
