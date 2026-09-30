from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pathlib import Path
from app.database.init_db import init_db
from app.api import system, channels, sources, tests, playlists, statistics, websocket, imports, scheduler as scheduler_api, remote_playlists, network
from app.core.logging import configure_logging
from app.core.scheduler import SchedulerService
from app.database.maintenance import cleanup_old_test_results
from app.core.version import version_string

scheduler = scheduler_api.scheduler_service

@asynccontextmanager
async def lifespan(app):
    configure_logging()
    init_db()
    cleanup_old_test_results()
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
