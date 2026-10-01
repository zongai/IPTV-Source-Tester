from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response, PlainTextResponse
from sqlalchemy import select, func

from app.api.auth import require_playlist_access
from app.database.database import SessionLocal
from app.database.models import ChannelDB, SourceDB, TestResultDB
from app.exporters.logo import resolve_tvg_logo
from app.exporters.m3u import render_m3u
from app.matcher.channel_matcher import channel_sort_key, rule_group_for_key
from app.core.config import get_settings
from app.utils.timeutil import to_iso

router = APIRouter()


def subscription_filename(
    *,
    ext: str,
    min_score: float | None = None,
    min_stability: float | None = None,
    min_height: int = 0,
    min_speed: float | None = None,
) -> str:
    """Build a descriptive download name for saved subscription files.

    Example: iptv-s70-h720-20260930.m3u
    """
    settings = get_settings()
    score = settings.min_score if min_score is None else min_score
    stability = settings.min_stability if min_stability is None else min_stability
    speed = 0 if min_speed is None else min_speed
    parts = ["iptv", f"s{int(score) if float(score).is_integer() else score}"]
    if min_height and min_height > 0:
        parts.append(f"h{int(min_height)}")
    if stability and float(stability) > 0 and float(stability) != float(settings.min_stability):
        # only append when caller overrides default, keep names short otherwise
        parts.append(f"st{int(float(stability) * 100)}")
    if speed and float(speed) > 0:
        parts.append(f"sp{int(speed) if float(speed).is_integer() else speed}")
    parts.append(datetime.utcnow().strftime("%Y%m%d"))
    name = "-".join(str(p) for p in parts)
    ext = ext.lstrip(".")
    return f"{name}.{ext}"


def _content_disposition(filename: str) -> str:
    # ASCII fallback + RFC 5987 filename* for players/browsers.
    safe = filename.encode("ascii", "ignore").decode("ascii") or f"iptv.{filename.rsplit('.', 1)[-1]}"
    from urllib.parse import quote
    return f"attachment; filename=\"{safe}\"; filename*=UTF-8''{quote(filename)}"


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
            logo = resolve_tvg_logo(c.display_name, c.tvg_logo, channel_id=c.id)
            # Unified rule-based group (央视/卫视/其他), never playlist group-title.
            ch_group = c.group_name or rule_group_for_key(c.id, c.display_name)
            bucket = grouped.setdefault(c.id, {
                'id': c.id, 'name': c.display_name, 'logo': logo,
                'group': ch_group, 'sources': [],
            })
            bucket['sources'].append({
                'id': x.id, 'url': x.url,
                'group': ch_group,
                'user_agent': x.user_agent, 'referer': x.referer,
                'origin': x.origin, 'cookie': x.cookie, 'authorization': x.authorization,
                'resolution': r.height, 'bitrate': r.bitrate,
                'score': r.score, 'stability': r.stability, 'speed': r.download_speed,
                'latency': r.ttfb * 1000 if r.ttfb else None,
                'tested_at': to_iso(r.tested_at),
            })
        out = list(grouped.values())
        out.sort(key=lambda c: channel_sort_key(c.get('id') or c.get('name') or ''))
        for c in out:
            # Backup lines: higher score / resolution first.
            c['sources'].sort(
                key=lambda z: (
                    z['score'] or 0,
                    z.get('resolution') or 0,
                    z['stability'] or 0,
                    z['speed'] or 0,
                ),
                reverse=True,
            )
        return {'channels': out, 'channel_count': len(out), 'source_count': sum(len(c['sources']) for c in out)}


def _query_filters(min_score=None, min_stability=None, min_height=0, min_speed=None):
    settings = get_settings()
    return payload(
        min_score=settings.min_score if min_score is None else min_score,
        min_stability=settings.min_stability if min_stability is None else min_stability,
        min_height=min_height,
        min_speed=0 if min_speed is None else min_speed,
    )


def _m3u_response(
    min_score: float | None = None,
    min_stability: float | None = None,
    min_height: int = 0,
    min_speed: float | None = None,
    *,
    download: bool = False,
):
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
            group_title = c.get('group') or rule_group_for_key(c.get('id') or '', c.get('name')) or ''
            # tvg-id / tvg-name must match EPG channel id (e.g. CCTV1), not internal key.
            epg_name = c.get('name') or c.get('id') or ''
            entries.append({'name': epg_name, 'url': source['url'], 'attrs': {
                'tvg-id': epg_name, 'tvg-name': epg_name, 'tvg-logo': c['logo'],
                'group-title': group_title,
            }, 'headers': headers})
    # Group (央视/卫视/其他) then CCTV numeric order — not lexicographic name.
    _gorder = {'央视': 0, '卫视': 1, '其他': 2}
    entries.sort(key=lambda e: (
        _gorder.get((e.get('attrs') or {}).get('group-title') or '', 9),
        channel_sort_key((e.get('attrs') or {}).get('tvg-id') or e.get('name') or ''),
    ))
    resp_headers = {
        'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
        'Pragma': 'no-cache',
    }
    if download:
        filename = subscription_filename(
            ext='m3u', min_score=min_score, min_stability=min_stability,
            min_height=min_height, min_speed=min_speed,
        )
        resp_headers['Content-Disposition'] = _content_disposition(filename)
    return Response(content=render_m3u(entries), media_type='audio/x-mpegurl', headers=resp_headers)


def _json_response(
    min_score: float | None = None,
    min_stability: float | None = None,
    min_height: int = 0,
    min_speed: float | None = None,
    *,
    download: bool = False,
):
    data = _query_filters(min_score, min_stability, min_height, min_speed)
    if not download:
        return data
    filename = subscription_filename(
        ext='json', min_score=min_score, min_stability=min_stability,
        min_height=min_height, min_speed=min_speed,
    )
    return JSONResponse(
        content=data,
        headers={
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Content-Disposition': _content_disposition(filename),
        },
    )


@router.get('/playlists/json', dependencies=[Depends(require_playlist_access)])
def json_playlist(
    min_score: float | None = Query(None, ge=0, le=100),
    min_stability: float | None = Query(None, ge=0, le=1),
    min_height: int = Query(0, ge=0),
    min_speed: float | None = Query(None, ge=0),
    download: bool = Query(False),
):
    return _json_response(min_score, min_stability, min_height, min_speed, download=download)


@router.get('/player/channels', dependencies=[Depends(require_playlist_access)])
def player_channels(min_score: float | None = Query(None, ge=0, le=100), min_stability: float | None = Query(None, ge=0, le=1), min_height: int = Query(0, ge=0), min_speed: float | None = Query(None, ge=0)):
    return _query_filters(min_score, min_stability, min_height, min_speed)


@router.get('/playlists/m3u', response_class=PlainTextResponse, dependencies=[Depends(require_playlist_access)])
def m3u(
    min_score: float | None = Query(None, ge=0, le=100),
    min_stability: float | None = Query(None, ge=0, le=1),
    min_height: int = Query(0, ge=0),
    min_speed: float | None = Query(None, ge=0),
    download: bool = Query(False),
):
    return _m3u_response(min_score, min_stability, min_height, min_speed, download=download)


@router.get('/subscription/m3u', response_class=PlainTextResponse, dependencies=[Depends(require_playlist_access)])
def subscription_m3u(
    min_score: float | None = Query(None, ge=0, le=100),
    min_stability: float | None = Query(None, ge=0, le=1),
    min_height: int = Query(0, ge=0),
    min_speed: float | None = Query(None, ge=0),
    download: bool = Query(False),
):
    return _m3u_response(min_score, min_stability, min_height, min_speed, download=download)


@router.get('/subscription/json', dependencies=[Depends(require_playlist_access)])
def subscription_json(
    min_score: float | None = Query(None, ge=0, le=100),
    min_stability: float | None = Query(None, ge=0, le=1),
    min_height: int = Query(0, ge=0),
    min_speed: float | None = Query(None, ge=0),
    download: bool = Query(False),
):
    return _json_response(min_score, min_stability, min_height, min_speed, download=download)
