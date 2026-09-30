from fastapi import APIRouter, Depends
from sqlalchemy import select
from app.api.auth import require_admin
from app.database.database import SessionLocal
from app.database.models import ChannelDB, SourceDB, TestResultDB
from app.matcher.channel_matcher import channel_sort_key

router = APIRouter()


def _latest(session, source_id, validated_only=False):
    stmt = select(TestResultDB).where(TestResultDB.source_id == source_id)
    if validated_only:
        stmt = stmt.where(TestResultDB.segment_valid.is_not(None))
    return session.scalars(stmt.order_by(TestResultDB.tested_at.desc()).limit(1)).first()


@router.get('/channels', dependencies=[Depends(require_admin)])
def channels():
    with SessionLocal() as s:
        out = []
        for c in s.scalars(select(ChannelDB)).unique():
            results = []
            for x in c.sources:
                r = _latest(s, x.id, validated_only=True)
                results.append({
                    'id': x.id,
                    'url': x.url,
                    'status': x.status,
                    'enabled': x.enabled,
                    'score': r.score if r else None,
                    'height': r.height if r else None,
                    'speed': r.download_speed if r else None,
                    'ttfb': r.ttfb if r else None,
                    'segment_valid': r.segment_valid if r else None,
                    'error_type': r.error_type if r else None,
                    'error_message': r.error_message if r else None,
                    'tested_at': r.tested_at.isoformat() if r else None,
                })
            out.append({'id': c.id, 'name': c.display_name, 'sources': len(c.sources), 'results': results})
        out.sort(key=lambda c: channel_sort_key(c['name']))
        return out


@router.get('/channels/{channel_id}', dependencies=[Depends(require_admin)])
def channel(channel_id):
    with SessionLocal() as s:
        c = s.get(ChannelDB, channel_id)
        return {'id': c.id, 'name': c.display_name, 'aliases': c.aliases_json, 'source_count': len(c.sources)} if c else {'error': 'not_found'}


@router.get('/channels/{channel_id}/sources', dependencies=[Depends(require_admin)])
def channel_sources(channel_id):
    with SessionLocal() as s:
        out = []
        for x in s.scalars(select(SourceDB).where(SourceDB.channel_id == channel_id)):
            r = _latest(s, x.id, validated_only=True)
            out.append({
                'id': x.id,
                'url': x.url,
                'status': x.status,
                'score': r.score if r else None,
                'resolution': r.height if r else None,
                'bitrate': r.bitrate if r else None,
                'speed': r.download_speed if r else None,
                'latency': r.ttfb * 1000 if r and r.ttfb else None,
                'segment_valid': r.segment_valid if r else None,
                'error_type': r.error_type if r else None,
                'error_message': r.error_message if r else None,
                'tested_at': r.tested_at.isoformat() if r else None,
            })
        return out
