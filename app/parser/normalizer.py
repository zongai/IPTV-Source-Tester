import re
from urllib.parse import urlsplit, urlunsplit


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("\ufeff", "").strip()


def normalize_header(value: str | None) -> str | None:
    """Treat None / blank / whitespace-only headers as the same (None)."""
    if value is None:
        return None
    text = str(value).replace("\ufeff", "").strip()
    return text or None


def normalize_url(url: str) -> str:
    """Normalize scheme/host/path while preserving IPv6 brackets and query tokens."""
    url = _clean_text(url)
    p = urlsplit(url)
    if not p.scheme or not p.netloc:
        return url

    scheme = p.scheme.lower()
    host = (p.hostname or "").lower()
    if not host:
        return url

    # urlsplit strips brackets from IPv6 hostname; put them back for a valid URL.
    if ":" in host and not host.startswith("["):
        host_part = f"[{host}]"
    else:
        host_part = host

    userinfo = ""
    if p.username is not None:
        userinfo = p.username + ((":" + p.password) if p.password is not None else "") + "@"

    try:
        port = p.port
    except ValueError:
        # Illegal port in netloc — keep original URL rather than crashing import.
        return url

    default = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = userinfo + host_part + (f":{port}" if port and not default else "")
    path = p.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, p.query, ""))


def normalize_channel_name(name: str) -> str:
    """Legacy helper: prefer matcher.resolve_channel for new code."""
    from app.matcher.channel_matcher import resolve_channel

    ident = resolve_channel(display_name=name)
    # Prefer EPG-aligned display (CCTV1 / CCTV5+ / 湖南卫视).
    if ident.display_name:
        return ident.display_name
    m = __import__("re").fullmatch(r"cctv-(\d+)(-plus)?", ident.key)
    if m:
        base = f"CCTV{m.group(1)}"
        return base + ("+" if m.group(2) else "")
    if ident.key == "cctv-4k":
        return "CCTV4K"
    return (name or "").upper()


def infer_default_group(*names: str | None) -> str | None:
    """Rule-based group (央视 / 卫视 / 其他); does not use playlist group-title."""
    from app.matcher.channel_matcher import resolve_channel

    for raw in names:
        text = _clean_text(raw)
        if not text:
            continue
        return resolve_channel(display_name=text).group
    return None


def source_identity_key(
    normalized_url: str,
    user_agent: str | None = None,
    referer: str | None = None,
    origin: str | None = None,
    cookie: str | None = None,
    authorization: str | None = None,
) -> tuple:
    """Dedup key: URL + headers, with None and empty headers equivalent."""
    return (
        normalized_url,
        normalize_header(user_agent),
        normalize_header(referer),
        normalize_header(origin),
        normalize_header(cookie),
        normalize_header(authorization),
    )
