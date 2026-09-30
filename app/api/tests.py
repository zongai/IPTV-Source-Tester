import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.auth import require_admin
from app.api.websocket import broadcast
from app.database.database import SessionLocal
from app.database.locks import db_write_lock
from app.database.models import SourceDB, TestResultDB
from app.database.repository import maybe_auto_delete_failed_source, retain_ffprobe_media_fields
from app.services.test_service import TestRunner

router = APIRouter()
jobs = {}
_job_tasks = {}

_RESULT_FIELDS = (
    'dns_latency', 'ttfb', 'http_status', 'content_type', 'playlist_valid',
    'segment_valid', 'video_codec', 'audio_codec', 'width', 'height', 'fps',
    'bitrate', 'download_speed', 'min_speed', 'max_speed', 'startup_time',
    'stability', 'failure_rate', 'score', 'error_type', 'error_message',
    'ffprobe_json',
)


async def run_job(job_id, deep=True, source_ids=None, mode=None):
    jobs[job_id]['status'] = 'running'
    session = SessionLocal()
    runner = TestRunner()
    try:
        q = select(SourceDB)
        if source_ids:
            q = q.where(SourceDB.id.in_(source_ids))
        sources = list(session.scalars(q))
        session.close()
        session = None
        jobs[job_id]['total'] = len(sources)
        completed = 0

        async def save_result(index, source, result):
            nonlocal completed
            if isinstance(result, Exception):
                result = {
                    'segment_valid': False, 'playlist_valid': False,
                    'error_type': 'INTERNAL_ERROR', 'error_message': str(result)[:1000],
                }
            # Never share one SQLAlchemy Session between concurrent test callbacks.
            async with db_write_lock:
                write_session = SessionLocal()
                try:
                    # Carry forward last FFprobe resolution when this mode cannot measure it.
                    result = retain_ffprobe_media_fields(write_session, source.id, result)
                    data = {k: result.get(k) for k in _RESULT_FIELDS}
                    write_session.add(TestResultDB(source_id=source.id, tested_at=datetime.utcnow(), **data))
                    src_db = write_session.get(SourceDB, source.id)
                    if src_db and result.get('segment_valid') is not None:
                        src_db.status = 'active' if result.get('segment_valid') else 'temporarily_failed'
                    # Persist the failure row first so consecutive-failure counting includes it.
                    write_session.flush()
                    if result.get('segment_valid') is False:
                        maybe_auto_delete_failed_source(write_session, source.id)
                    write_session.commit()
                except Exception as exc:
                    write_session.rollback()
                    jobs[job_id]['save_errors'] = jobs[job_id].get('save_errors', 0) + 1
                    jobs[job_id]['last_error'] = str(exc)[:500]
                finally:
                    write_session.close()
            completed += 1
            jobs[job_id]['progress'] = completed
            await broadcast({'job_id': job_id, 'progress': completed, 'total': len(sources)})

        await runner.test_many(sources, deep=deep, mode=mode, on_result=save_result)
        if jobs[job_id].get('status') != 'stop_requested':
            jobs[job_id]['status'] = 'completed'
    except asyncio.CancelledError:
        jobs[job_id]['status'] = 'stop_requested'
    
    except Exception as exc:
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(exc)
    finally:
        if session is not None:
            session.close()
        _job_tasks.pop(job_id, None)


@router.post('/tests/start', dependencies=[Depends(require_admin)])
async def start(deep: bool = False, source_ids: str | None = None, mode: str | None = 'standard'):
    if mode not in (None, 'quick', 'standard', 'full'):
        mode = None
    if mode:
        deep = mode == 'full'
    job_id = str(uuid.uuid4())
    try:
        ids = [int(x.strip()) for x in source_ids.split(',') if x.strip()] if source_ids else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='source_ids must be comma-separated integers') from exc
    jobs[job_id] = {
        'id': job_id, 'status': 'queued', 'progress': 0, 'total': 0,
        'mode': mode or ('full' if deep else 'standard'),
    }
    _job_tasks[job_id] = asyncio.create_task(run_job(job_id, deep, ids, mode))
    return jobs[job_id]


@router.post('/tests/stop', dependencies=[Depends(require_admin)])
async def stop(job_id: str):
    if job_id not in jobs:
        return {'error': 'not_found'}
    task = _job_tasks.get(job_id)
    if task and not task.done():
        jobs[job_id]['status'] = 'stop_requested'
        task.cancel()
    return jobs[job_id]


@router.get('/tests/active', dependencies=[Depends(require_admin)])
async def active_jobs():
    return [v for v in jobs.values() if v.get('status') in ('queued', 'running', 'stop_requested')]

@router.get('/tests/{job_id}', dependencies=[Depends(require_admin)])
async def status(job_id):
    return jobs.get(job_id, {'error': 'not_found'})
