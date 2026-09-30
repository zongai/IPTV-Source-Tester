import re
from urllib.parse import urlsplit, urlunsplit


def _clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("\ufeff", "").strip()


def normalize_url(url: str) -> str:
    # Do not unquote the entire URL: %2F, %26, signed tokens and other query
    # parameters can be semantically significant. Normalize only host/scheme
    # and harmless trailing path slashes.
    url = _clean_text(url)
    p = urlsplit(url)
    if not p.scheme or not p.netloc:
        return url
    host = p.hostname.lower() if p.hostname else ""
    userinfo = ""
    if p.username is not None:
        userinfo = p.username + ((":" + p.password) if p.password is not None else "") + "@"
    port = p.port
    default = (p.scheme.lower() == "http" and port == 80) or (p.scheme.lower() == "https" and port == 443)
    netloc = userinfo + host + (f":{port}" if port and not default else "")
    path = p.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((p.scheme.lower(), netloc, path, p.query, ""))


def normalize_channel_name(name: str) -> str:
    s = _clean_text(name).casefold()
    s = re.sub(r"[\s_]+", " ", s)
    s = re.sub(r"\s*-\s*", "-", s)
    s = s.replace("中央电视台", "cctv")
    # CCTV5 and CCTV5+ are distinct channels. Keep the plus marker in the
    # canonical name instead of letting generic punctuation stripping merge it.
    s = re.sub(r"cctv\s*-?\s*([0-9]+)\s*(?:\+|plus)", r"cctv-\1-plus", s)
    s = re.sub(r"cctv\s*-?\s*([0-9]+)\s*综合", r"cctv-\1", s)
    s = re.sub(r"cctv\s*-?\s*([0-9]+)", r"cctv-\1", s)
    return re.sub(r"\s+", " ", s).strip().upper()
