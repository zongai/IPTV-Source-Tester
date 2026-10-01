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
    s = _clean_text(name).casefold()
    s = re.sub(r"[\s_]+", " ", s)
    s = re.sub(r"\s*-\s*", "-", s)
    s = s.replace("中央电视台", "cctv")
    # CCTV5 and CCTV5+ are distinct channels. Keep the plus marker.
    # Avoid \b after '+' (non-word); end-of-string would not match.
    s = re.sub(r"cctv\s*-?\s*([0-9]+)\s*(?:\+|plus)(?!\w)", r"cctv-\1-plus", s)
    s = re.sub(r"cctv\s*-?\s*([0-9]+)\s*综合", r"cctv-\1", s)
    s = re.sub(r"cctv\s*-?\s*([0-9]+)(?!\w)", r"cctv-\1", s)
    return re.sub(r"\s+", " ", s).strip().upper()


def infer_default_group(*names: str | None) -> str | None:
    """Default group-title when M3U has none: CCTV → 央视频道, 卫视 → 卫视频道."""
    for raw in names:
        text = _clean_text(raw)
        if not text:
            continue
        # Prefer explicit CCTV / 中央电视台 markers over generic 卫视.
        folded = text.casefold()
        if "cctv" in folded or "中央电视台" in text:
            return "央视频道"
        if "卫视" in text:
            return "卫视频道"
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
