from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, PlainTextResponse
from sqlalchemy import select, func

from app.api.auth import require_playlist_access
from app.database.database import SessionLocal
from app.database.models import ChannelDB, SourceDB, TestResultDB
from app.exporters.m3u import render_m3u
from app.matcher.channel_matcher import channel_sort_key
from app.core.config import get_settings

router = APIRouter()


def _latest_validated_subquery():
    ranked = select(
        TestResultDB.id.label('result_id'),
        TestResultDB.source_id.label('source_id'),
        func.row_number().over(
            partition_by=TestResultDB.source_id,
            order_by=TestResultDB.tested_at.desc(),
        ).label('rn'),
    ).where(TestResultDB.segment_valid.is_not(None)).subquery()
    return ranked


def payload(min_score=0.0, min_stability=0.0, min_height=0, min_speed=0.0):
    """Return only sources with the latest validated result passing filters."""
    ranked = _latest_validated_subquery()
    stmt = (
        select(ChannelDB, SourceDB, TestResultDB)
        .join(SourceDB, SourceDB.channel_id == ChannelDB.id)
        .join(ranked, ranked.c.source_id == SourceDB.id)
        .join(TestResultDB, TestResultDB.id == ranked.c.result_id)
        .where(ranked.c.rn == 1, SourceDB.enabled.is_(True), SourceDB.status != 'temporarily_failed', SourceDB.status != 'inactive')
        .order_by(ChannelDB.id)
    )
    with SessionLocal() as s:
        grouped = {}
        for c, x, r in s.execute(stmt):
            if r.segment_valid is not True:
                continue
            if (r.score or 0) < min_score:
                continue
            if r.stability is not None and r.stability < min_stability:
                continue
            if (r.height or 0) < min_height:
                continue
            if (r.download_speed or 0) < min_speed:
                continue
            grouped.setdefault(c.id, {'id': c.id, 'name': c.display_name, 'logo': c.tvg_logo,
                                      'group': c.group_name, 'sources': []})['sources'].append({
                'id': x.id, 'url': x.url, 'user_agent': x.user_agent, 'referer': x.referer,
                'origin': x.origin, 'cookie': x.cookie, 'authorization': x.authorization, 'resolution': r.height, 'bitrate': r.bitrate,
                'score': r.score, 'stability': r.stability, 'speed': r.download_speed,
                'latency': r.ttfb * 1000 if r.ttfb else None, 'tested_at': r.tested_at.isoformat(),
            })
        out = list(grouped.values())
        out.sort(key=lambda c: channel_sort_key(c['name']))
        for c in out:
            c['sources'].sort(key=lambda z: (z['score'] or 0, z['stability'] or 0, z['speed'] or 0), reverse=True)
        return {'channels': out, 'channel_count': len(out), 'source_count': sum(len(c['sources']) for c in out)}


def _query_filters(min_score=None, min_stability=None, min_height=0, min_speed=None):
    settings = get_settings()
    return payload(
        min_score=settings.min_score if min_score is None else min_score,
        min_stability=settings.min_stability if min_stability is None else min_stability,
        min_height=min_height,
        min_speed=0 if min_speed is None else min_speed,
    )


@router.get('/playlists/json', dependencies=[Depends(require_playlist_access)])
def json_playlist(min_score: float | None = Query(None, ge=0, le=100), min_stability: float | None = Query(None, ge=0, le=1), min_height: int = Query(0, ge=0), min_speed: float | None = Query(None, ge=0)):
    return _query_filters(min_score, min_stability, min_height, min_speed)


@router.get('/player/channels', dependencies=[Depends(require_playlist_access)])
def player_channels(min_score: float | None = Query(None, ge=0, le=100), min_stability: float | None = Query(None, ge=0, le=1), min_height: int = Query(0, ge=0), min_speed: float | None = Query(None, ge=0)):
    return _query_filters(min_score, min_stability, min_height, min_speed)


@router.get('/playlists/m3u', response_class=PlainTextResponse, dependencies=[Depends(require_playlist_access)])
def m3u(min_score: float | None = Query(None, ge=0, le=100), min_stability: float | None = Query(None, ge=0, le=1), min_height: int = Query(0, ge=0), min_speed: float | None = Query(None, ge=0)):
    data = _query_filters(min_score, min_stability, min_height, min_speed)
    entries = []
    for c in data['channels']:
        for source in c['sources']:
            headers = {}
            if source.get('user_agent'):
                headers['User-Agent'] = source['user_agent']
            if source.get('referer'):
                headers['Referer'] = source['referer']
            if source.get('origin'):
                headers['Origin'] = source['origin']
            if source.get('cookie'):
                headers['Cookie'] = source['cookie']
            if source.get('authorization'):
                headers['Authorization'] = source['authorization']
            entries.append({'name': c['name'], 'url': source['url'], 'attrs': {
                'tvg-id': c['id'], 'tvg-name': c['name'], 'tvg-logo': c['logo'], 'group-title': c['group'] or '',
            }, 'headers': headers})
    return Response(content=render_m3u(entries), media_type='audio/x-mpegurl',
                    headers={'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0', 'Pragma': 'no-cache'})


@router.get('/subscription/m3u', response_class=PlainTextResponse, dependencies=[Depends(require_playlist_access)])
def subscription_m3u(min_score: float | None = Query(None, ge=0, le=100), min_stability: float | None = Query(None, ge=0, le=1), min_height: int = Query(0, ge=0), min_speed: float | None = Query(None, ge=0)):
    return m3u(min_score, min_stability, min_height, min_speed)


@router.get('/subscription/json', dependencies=[Depends(require_playlist_access)])
def subscription_json(min_score: float | None = Query(None, ge=0, le=100), min_stability: float | None = Query(None, ge=0, le=1), min_height: int = Query(0, ge=0), min_speed: float | None = Query(None, ge=0)):
    return _query_filters(min_score, min_stability, min_height, min_speed)
