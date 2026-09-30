from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.api.auth import require_admin
from app.core.scheduler import scheduler_service

router = APIRouter()

class SchedulerUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=10080)
    test_mode: str | None = None
    source_scope: str | None = None
    stale_hours: int | None = Field(default=None, ge=1, le=8760)
    max_concurrency: int | None = Field(default=None, ge=1, le=200)
    max_host_concurrency: int | None = Field(default=None, ge=1, le=50)
    connect_timeout: int | None = Field(default=None, ge=1, le=120)
    read_timeout: int | None = Field(default=None, ge=1, le=300)
    segment_test_count: int | None = Field(default=None, ge=1, le=10)


def serialize(d):
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in d.items()}

@router.get('/scheduler', dependencies=[Depends(require_admin)])
async def get_scheduler():
    return serialize(scheduler_service.status())

@router.get('/scheduler/runs', dependencies=[Depends(require_admin)])
async def get_scheduler_runs(limit: int = 20):
    return [serialize(x) for x in scheduler_service.runs(limit)]


@router.put('/scheduler', dependencies=[Depends(require_admin)])
async def update_scheduler(body: SchedulerUpdate):
    if body.test_mode not in (None, 'quick', 'standard', 'full'):
        raise HTTPException(400, 'test_mode must be quick, standard or full')
    if body.source_scope not in (None, 'enabled', 'failed', 'stale'):
        raise HTTPException(400, 'source_scope must be enabled, failed or stale')
    return serialize(scheduler_service.update(**body.model_dump(exclude_none=True)))

@router.post('/scheduler/run', dependencies=[Depends(require_admin)])
async def run_scheduler_now():
    return await scheduler_service.run_now(trigger='manual')
