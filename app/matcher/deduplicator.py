from app.parser.normalizer import normalize_url

def source_key(url, headers=None):
    headers = headers or {}
    relevant = tuple(sorted((k.lower(), v) for k, v in headers.items()
                            if k.lower() in {"user-agent","referer","origin","cookie","authorization"}))
    return normalize_url(url), relevant
