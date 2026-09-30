from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends

from app.api.auth import require_admin
from app.core.config import get_settings
from app.core.version import code_revision, version_string

router = APIRouter()


def _redact_database_url(url: str) -> str:
    """Hide credentials in database URLs returned by status endpoints."""
    try:
        p = urlsplit(url)
        if not p.scheme:
            return url
        host = p.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        auth = ""
        if p.username is not None:
            auth = "***:***@" if p.password is not None else "***@"
        port = f":{p.port}" if p.port else ""
        netloc = f"{auth}{host}{port}"
        return urlunsplit((p.scheme, netloc, p.path, "", ""))
    except Exception:
        return "[redacted]"


@router.get("/system/version")
async def version():
    return {"version": version_string(), "revision": code_revision()}


@router.get("/system/status", dependencies=[Depends(require_admin)])
async def status():
    s = get_settings()
    return {
        "status": "ok",
        "version": version_string(),
        "revision": code_revision(),
        "database_url": _redact_database_url(s.database_url),
        "max_concurrency": s.max_concurrency,
    }
