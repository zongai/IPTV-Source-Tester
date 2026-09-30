from fastapi import APIRouter, Depends
from app.api.auth import require_admin
from app.core.config import get_settings
from app.core.version import version_string, code_revision

router = APIRouter()


@router.get('/system/version')
async def version():
    return {'version': version_string(), 'revision': code_revision()}


@router.get('/system/status', dependencies=[Depends(require_admin)])
async def status():
    s = get_settings()
    return {
        'status': 'ok',
        'version': version_string(),
        'revision': code_revision(),
        'database_url': s.database_url,
        'max_concurrency': s.max_concurrency,
    }
