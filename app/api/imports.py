from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.auth import require_admin
from app.database.database import SessionLocal
from app.database.locks import db_write_lock
from app.parser.source import parse_playlist_source
from app.services.import_service import import_entries

router = APIRouter()


class ImportURLRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)


async def _import_entries(entries, playlist_name: str):
    """Run synchronous DB import off the event loop so tests keep progressing."""
    import asyncio

    async with db_write_lock:
        def _work():
            with SessionLocal() as s:
                return import_entries(s, entries, playlist_name)

        return await asyncio.to_thread(_work)


@router.post('/playlists/import', dependencies=[Depends(require_admin)])
async def import_playlist(payload: ImportURLRequest):
    """Import a remote HTTP/HTTPS M3U/M3U8 playlist URL."""
    source = payload.url.strip()
    if not source.lower().startswith(('http://', 'https://')):
        raise HTTPException(400, 'Only HTTP/HTTPS playlist URLs are accepted')
    try:
        entries = await parse_playlist_source(source)
        result = await _import_entries(entries, source)
        result.update({'source': source, 'type': 'url'})
        return result
    except Exception as e:
        raise HTTPException(400, f'Playlist import failed: {e}') from e


@router.post('/playlists/import-file', dependencies=[Depends(require_admin)])
async def import_playlist_file(file: UploadFile = File(...)):
    """Import an uploaded local M3U/M3U8 file."""
    name = Path(file.filename or 'playlist.m3u').name
    if not name.lower().endswith(('.m3u', '.m3u8', '.txt')):
        raise HTTPException(400, 'Only .m3u, .m3u8 or .txt playlist files are accepted')

    data = await file.read()
    if not data:
        raise HTTPException(400, 'Uploaded playlist is empty')
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, 'Playlist file is too large; maximum is 50 MB')

    text = data.decode('utf-8-sig', errors='replace')
    try:
        # Parse directly so the upload never needs to be persisted permanently.
        from app.parser.m3u import parse_m3u
        entries = parse_m3u(text)
        result = await _import_entries(entries, name)
        result.update({'source': name, 'type': 'file'})
        return result
    except Exception as e:
        raise HTTPException(400, f'Playlist import failed: {e}') from e
