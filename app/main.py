from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.api import (
    channels,
    imports,
    network,
    playlists,
    remote_playlists,
    scheduler as scheduler_api,
    sources,
    statistics,
    system,
    tests,
    websocket,
)
from app.core.logging import configure_logging
from app.core.version import version_string
from app.database.database import SessionLocal
from app.database.init_db import init_db
from app.database.locks import db_write_lock
from app.database.maintenance import cleanup_old_test_results
from app.services.import_service import dedupe_sources, refresh_epg_names

scheduler = scheduler_api.scheduler_service


@asynccontextmanager
async def lifespan(app):
    configure_logging()
    init_db()
    try:
        cleanup_old_test_results()
    except Exception:
        pass
    # One-shot repair of historical duplicates (None vs empty headers).
    try:
        async with db_write_lock:
            with SessionLocal() as session:
                removed = dedupe_sources(session)
                if removed:
                    session.commit()
    except Exception:
        pass
    # Align display names with EPG channel ids (tvg-id matching).
    try:
        async with db_write_lock:
            with SessionLocal() as session:
                n = refresh_epg_names(session)
                if n:
                    session.commit()
    except Exception:
        pass
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()

app = FastAPI(title='IPTV Source Tester V4', version=version_string(), lifespan=lifespan)
for r in (system, channels, sources, tests, playlists, statistics, imports, scheduler_api, remote_playlists, network):
    app.include_router(r.router, prefix='/api')
app.include_router(websocket.router)

@app.get('/', response_class=HTMLResponse)
async def root():
    index = Path(__file__).resolve().parent.parent / 'frontend' / 'index.html'
    return HTMLResponse(index.read_text(encoding='utf-8'))

@app.get('/health')
async def health():
    return {'status': 'ok'}
