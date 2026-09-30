from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from app.api.auth import require_admin
from app.database.database import SessionLocal
from app.database.models import ChannelDB, SourceDB, TestResultDB

router = APIRouter()


@router.get('/statistics', dependencies=[Depends(require_admin)])
def stats():
    with SessionLocal() as s:
        # Use the latest validated result per source rather than averaging every
        # historical test. This makes the dashboard represent current quality.
        latest = {}
        for source_id, tested_at, score in s.execute(
            select(TestResultDB.source_id, TestResultDB.tested_at, TestResultDB.score)
            .where(TestResultDB.segment_valid.is_not(None))
            .order_by(TestResultDB.source_id, TestResultDB.tested_at.desc())
        ):
            if source_id not in latest:
                latest[source_id] = (tested_at, score)
        scores = [v[1] for v in latest.values() if v[1] is not None]
        return {
            'channels': s.scalar(select(func.count(ChannelDB.id))) or 0,
            'sources': s.scalar(select(func.count(SourceDB.id))) or 0,
            'active_sources': s.scalar(select(func.count(SourceDB.id)).where(SourceDB.status == 'active')) or 0,
            'tested_sources': len(latest),
            'average_score': sum(scores) / len(scores) if scores else None,
        }
