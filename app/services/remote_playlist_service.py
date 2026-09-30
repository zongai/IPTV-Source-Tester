from datetime import datetime

import aiohttp

from app.core.config import get_settings
from app.database.database import SessionLocal
from app.database.locks import db_write_lock
from app.database.models import RemotePlaylistDB
from app.parser.m3u import parse_m3u
from app.services.import_service import import_entries


# These status codes mean the configured remote URL is not usable with the
# current configuration. They are not treated as transient network failures.
PERMANENT_HTTP_FAILURES = {400, 401, 403, 404, 410, 422}


def _failure_is_permanent_http(status: int | None) -> bool:
    return status in PERMANENT_HTTP_FAILURES


def _auto_delete_locked(session, playlist: RemotePlaylistDB, reason: str):
    """Delete only the remote-playlist configuration.

    Imported channels/sources are intentionally retained: the application has
    no ownership/provenance contract that would make deleting them safe.
    """
    playlist_id = playlist.id
    name = playlist.name
    url = playlist.url
    now = datetime.utcnow()
    playlist.last_fetched_at = now
    playlist.last_status = "auto_deleted"
    playlist.last_error = reason[:2000]
    playlist.auto_deleted_at = now
    session.delete(playlist)
    session.commit()
    return {
        "id": playlist_id,
        "name": name,
        "url": url,
        "auto_deleted": True,
        "reason": reason[:2000],
        "deleted_at": now.isoformat(),
    }


async def fetch_remote_playlist(playlist_id: int):
    with SessionLocal() as session:
        playlist = session.get(RemotePlaylistDB, playlist_id)
        if not playlist:
            raise ValueError(f"remote playlist {playlist_id} not found")
        url = playlist.url
        name = playlist.name or url

    settings = get_settings()
    timeout = aiohttp.ClientTimeout(total=120, connect=20, sock_connect=20, sock_read=60)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as client:
            async with client.get(url, allow_redirects=True) as response:
                status = response.status
                if status >= 400:
                    # Consume a bounded amount so the connection can be reused
                    # before raising/returning.
                    await response.read()
                    if _failure_is_permanent_http(status):
                        reason = f"remote playlist HTTP {status}; URL considered invalid"
                        with SessionLocal() as session:
                            playlist = session.get(RemotePlaylistDB, playlist_id)
                            if playlist:
                                async with db_write_lock:
                                    return _auto_delete_locked(session, playlist, reason)
                        raise ValueError(f"remote playlist {playlist_id} not found")
                    raise aiohttp.ClientResponseError(
                        response.request_info, response.history,
                        status=status, message=f"HTTP {status}", headers=response.headers,
                    )
                data = await response.read()

        text = data.decode("utf-8-sig", errors="replace")
        try:
            entries = parse_m3u(text)
        except Exception as exc:
            reason = f"invalid M3U content: {exc}"
            with SessionLocal() as session:
                playlist = session.get(RemotePlaylistDB, playlist_id)
                if playlist:
                    async with db_write_lock:
                        return _auto_delete_locked(session, playlist, reason)
            raise

        # A successful HTTP response containing no playlist entries is treated
        # as an invalid subscription rather than a successful empty refresh.
        if not entries:
            reason = "invalid M3U content: no playlist entries found"
            with SessionLocal() as session:
                playlist = session.get(RemotePlaylistDB, playlist_id)
                if playlist:
                    async with db_write_lock:
                        return _auto_delete_locked(session, playlist, reason)
            raise ValueError(f"remote playlist {playlist_id} not found")

        with SessionLocal() as session:
            playlist = session.get(RemotePlaylistDB, playlist_id)
            if not playlist:
                raise ValueError(f"remote playlist {playlist_id} not found")
            async with db_write_lock:
                result = import_entries(session, entries, name)
                playlist.last_fetched_at = datetime.utcnow()
                playlist.last_status = "success"
                playlist.last_added = int(result.get("added", 0))
                playlist.last_skipped = int(result.get("skipped", 0))
                playlist.last_error = None
                playlist.consecutive_failures = 0
                playlist.auto_deleted_at = None
                session.commit()
            return {
                "id": playlist.id,
                "name": playlist.name,
                "url": playlist.url,
                "entries": len(entries),
                "auto_deleted": False,
                **result,
                "fetched_at": playlist.last_fetched_at.isoformat(),
            }
    except Exception as exc:
        with SessionLocal() as session:
            playlist = session.get(RemotePlaylistDB, playlist_id)
            if not playlist:
                raise
            async with db_write_lock:
                failures = int(playlist.consecutive_failures or 0) + 1
                playlist.consecutive_failures = failures
                playlist.last_fetched_at = datetime.utcnow()
                playlist.last_status = "failed"
                playlist.last_error = str(exc)[:2000]
                threshold = settings.remote_playlist_max_failures
                if failures >= threshold:
                    return _auto_delete_locked(
                        session,
                        playlist,
                        f"remote playlist failed {failures} consecutive times; last error: {exc}",
                    )
                session.commit()
        raise
