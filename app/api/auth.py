from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.config import get_settings

# OpenAPI/Swagger exposes the standard Authorize button and sends:
# Authorization: Bearer <token>
bearer = HTTPBearer(auto_error=False)


async def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    """Require Bearer auth only when API_TOKEN is configured.

    If API_TOKEN is empty/unset, authentication is completely disabled and
    the endpoint can be used directly. This makes a private LAN deployment
    convenient while still allowing the same image to be secured later by
    setting API_TOKEN.
    """
    expected = get_settings().api_token.strip()
    if not expected:
        return

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="missing API token")

    if credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="invalid API token")


async def require_playlist_access(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    """Protect playlist endpoints when needed.

    PUBLIC_PLAYLIST=true always permits playlist access. Otherwise the normal
    API_TOKEN rule applies: no token configured means no authentication is
    required; a configured token requires a valid Bearer token.
    """
    settings = get_settings()
    if settings.public_playlist:
        return
    await require_admin(credentials)
