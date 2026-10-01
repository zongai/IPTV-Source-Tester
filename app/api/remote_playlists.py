from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.auth import require_admin
from app.database.database import SessionLocal
from app.database.models import RemotePlaylistDB
from app.core.scheduler import scheduler_service
from app.core.config import get_settings
from app.utils.timeutil import to_iso

router = APIRouter()


class RemotePlaylistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=8, max_length=4096)
    enabled: bool = True
    interval_minutes: int = Field(360, ge=1, le=10080)


class RemotePlaylistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=8, max_length=4096)
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=10080)


def _row(x):
    return {
        "id": x.id, "name": x.name, "url": x.url, "enabled": x.enabled,
        "interval_minutes": x.interval_minutes,
        "last_fetched_at": to_iso(x.last_fetched_at),
        "last_status": x.last_status, "last_added": x.last_added,
        "last_skipped": x.last_skipped, "last_error": x.last_error,
        "consecutive_failures": x.consecutive_failures or 0,
        "auto_delete_after_failures": get_settings().remote_playlist_max_failures,
        "auto_deleted_at": to_iso(x.auto_deleted_at),
        "updated_at": to_iso(x.updated_at),
    }


@router.get('/remote-playlists', dependencies=[Depends(require_admin)])
async def list_remote_playlists():
    with SessionLocal() as session:
        return [_row(x) for x in session.scalars(select(RemotePlaylistDB).order_by(RemotePlaylistDB.id)).all()]


@router.post('/remote-playlists', dependencies=[Depends(require_admin)])
async def create_remote_playlist(body: RemotePlaylistCreate):
    url = body.url.strip()
    if not url.lower().startswith(('http://', 'https://')):
        raise HTTPException(400, 'Only HTTP/HTTPS playlist URLs are accepted')
    with SessionLocal() as session:
        if session.scalar(select(RemotePlaylistDB).where(RemotePlaylistDB.url == url)):
            raise HTTPException(409, 'This remote playlist URL already exists')
        x = RemotePlaylistDB(name=body.name.strip(), url=url, enabled=body.enabled, interval_minutes=body.interval_minutes)
        session.add(x); session.commit(); session.refresh(x)
        result = _row(x)
    scheduler_service.schedule_remote_playlist(result['id'], result['interval_minutes'], result['enabled'])
    return result


@router.put('/remote-playlists/{playlist_id}', dependencies=[Depends(require_admin)])
async def update_remote_playlist(playlist_id: int, body: RemotePlaylistUpdate):
    with SessionLocal() as session:
        x = session.get(RemotePlaylistDB, playlist_id)
        if not x:
            raise HTTPException(404, 'Remote playlist not found')
        values = body.model_dump(exclude_none=True)
        if 'url' in values:
            values['url'] = values['url'].strip()
            if not values['url'].lower().startswith(('http://', 'https://')):
                raise HTTPException(400, 'Only HTTP/HTTPS playlist URLs are accepted')
            other = session.scalar(select(RemotePlaylistDB).where(RemotePlaylistDB.url == values['url'], RemotePlaylistDB.id != playlist_id))
            if other:
                raise HTTPException(409, 'This remote playlist URL already exists')
        for k, v in values.items(): setattr(x, k, v.strip() if k == 'name' else v)
        session.commit(); session.refresh(x)
        result = _row(x)
    scheduler_service.schedule_remote_playlist(result['id'], result['interval_minutes'], result['enabled'])
    return result


@router.delete('/remote-playlists/{playlist_id}', dependencies=[Depends(require_admin)])
async def delete_remote_playlist(playlist_id: int):
    with SessionLocal() as session:
        x = session.get(RemotePlaylistDB, playlist_id)
        if not x:
            raise HTTPException(404, 'Remote playlist not found')
        session.delete(x); session.commit()
    scheduler_service.unschedule_remote_playlist(playlist_id)
    return {'deleted': True, 'id': playlist_id}


@router.post('/remote-playlists/{playlist_id}/fetch', dependencies=[Depends(require_admin)])
async def fetch_remote_playlist_now(playlist_id: int):
    with SessionLocal() as session:
        if not session.get(RemotePlaylistDB, playlist_id):
            raise HTTPException(404, 'Remote playlist not found')
    try:
        return await scheduler_service.fetch_remote_playlist_now(playlist_id)
    except Exception as exc:
        raise HTTPException(400, f'Remote playlist fetch failed: {exc}') from exc
