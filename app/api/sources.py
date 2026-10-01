from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.auth import require_admin
from app.database.database import SessionLocal
from app.database.locks import db_write_lock
from app.database.models import SourceDB
from app.database.repository import list_failed_source_ids, purge_failed_sources
from app.services.statistics_service import history, summarize
from app.utils.timeutil import to_iso

router = APIRouter()


@router.get("/sources", dependencies=[Depends(require_admin)])
def sources():
    with SessionLocal() as s:
        return [
            {
                "id": x.id,
                "channel_id": x.channel_id,
                "url": x.url,
                "status": x.status,
                "enabled": x.enabled,
            }
            for x in s.scalars(select(SourceDB))
        ]


@router.get("/sources/failed", dependencies=[Depends(require_admin)])
def sources_failed_preview():
    """Preview how many sources would be removed by purge-failed."""
    with SessionLocal() as s:
        ids = list_failed_source_ids(s)
        return {"count": len(ids), "source_ids": ids}


@router.post("/sources/purge-failed", dependencies=[Depends(require_admin)])
async def sources_purge_failed():
    """Delete all failed/invalid sources in one step.

    Includes sources whose latest validated test failed, or whose status is
    temporarily_failed / inactive / failed. Untested sources are kept.
    Empty channels are removed automatically.
    """
    async with db_write_lock:
        with SessionLocal() as s:
            result = purge_failed_sources(s)
            s.commit()
            return result


@router.get("/sources/{source_id}", dependencies=[Depends(require_admin)])
def source(source_id: int):
    with SessionLocal() as s:
        x = s.get(SourceDB, source_id)
        return (
            {
                "id": x.id,
                "channel_id": x.channel_id,
                "url": x.url,
                "status": x.status,
                "enabled": x.enabled,
            }
            if x
            else {"error": "not_found"}
        )


@router.get("/sources/{source_id}/history", dependencies=[Depends(require_admin)])
def source_history(source_id: int, days: int = 7):
    with SessionLocal() as s:
        rows = history(s, source_id, days)
        return {
            "summary": summarize(rows),
            "results": [
                {
                    "id": r.id,
                    "tested_at": to_iso(r.tested_at),
                    "score": r.score,
                    "ttfb": r.ttfb,
                    "speed": r.download_speed,
                    "failure_rate": r.failure_rate,
                }
                for r in rows
            ],
        }
