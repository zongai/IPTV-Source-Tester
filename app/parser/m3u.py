import re
from urllib.parse import urljoin

from app.models.playlist import PlaylistEntry
from app.parser.normalizer import normalize_url

KNOWN = {
    "tvg-id", "tvg-name", "tvg-logo", "group-title",
    "tvg-language", "tvg-country", "tvg-shift", "radio",
}
_ATTR_RE = re.compile(r'([\w-]+)=(?:"([^"]*)"|([^\s,]+))')


def _clean(value):
    return (value or "").replace("\ufeff", "").strip()


def _split_extinf(line: str) -> tuple[str, str]:
    """Split EXTINF into (attr_region, display_name) honoring quoted commas."""
    # Body after "#EXTINF:"
    if ":" in line[:12]:
        body = line.split(":", 1)[1]
    else:
        body = line
    in_quotes = False
    last_comma = -1
    for i, ch in enumerate(body):
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            last_comma = i
    if last_comma < 0:
        return body, ""
    return body[:last_comma], body[last_comma + 1:]


def _parse_extinf(line):
    attr_region, name = _split_extinf(line)
    attrs = {
        m.group(1): _clean(m.group(2) if m.group(2) is not None else m.group(3))
        for m in _ATTR_RE.finditer(attr_region)
    }
    return attrs, _clean(name)


def _header_from_opt_key(raw_key: str) -> str | None:
    """Map EXTVLCOPT / EXTHTTP keys onto canonical header names."""
    key = raw_key.strip().lower()
    if key.startswith("http-"):
        key = key[5:]
    if key in {"user-agent", "http-user-agent"}:
        return "user-agent"
    if key in {"referer", "referrer", "http-referrer", "http-referer"}:
        return "referer"
    if key in {"origin", "http-origin"}:
        return "origin"
    if key in {"cookie", "http-cookie"}:
        return "cookie"
    if key in {"authorization", "http-authorization"}:
        return "authorization"
    return None


def parse_m3u(text: str, base_url: str | None = None) -> list[PlaylistEntry]:
    # Accept both normal UTF-8 and UTF-8-BOM playlists.
    text = text.lstrip("\ufeff")
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    entries, pending = [], None
    for line in lines:
        if line.startswith("#EXTINF"):
            attrs, name = _parse_extinf(line)
            pending = (attrs, name, line)
        elif line.startswith("#EXTVLCOPT:") and pending:
            payload = line.split(":", 1)[1]
            key, _, value = payload.partition("=")
            mapped = _header_from_opt_key(key)
            if mapped:
                pending[0]["__hdr__" + mapped] = _clean(value)
        elif line.startswith("#EXTHTTP:") and pending:
            payload = line.split(":", 1)[1]
            key, _, value = payload.partition("=")
            mapped = _header_from_opt_key(key)
            if mapped:
                pending[0]["__hdr__" + mapped] = _clean(value)
        elif not line.startswith("#") and pending:
            attrs, name, raw = pending
            headers = {}
            for k, v in attrs.items():
                if k.startswith("__hdr__"):
                    headers[k[len("__hdr__"):]] = _clean(v)
            try:
                url = normalize_url(urljoin(base_url, line) if base_url else line)
            except Exception:
                url = (urljoin(base_url, line) if base_url else line).strip()
            entries.append(PlaylistEntry(
                name=_clean(name),
                url=url,
                attributes={k: _clean(v) for k, v in attrs.items() if not k.startswith("__")},
                unknown_attributes={k: v for k, v in attrs.items() if k not in KNOWN and not k.startswith("__")},
                headers=headers,
                raw_extinf=raw,
                group=_clean(attrs.get("group-title")),
                tvg_id=_clean(attrs.get("tvg-id")),
                tvg_name=_clean(attrs.get("tvg-name")),
                tvg_logo=_clean(attrs.get("tvg-logo")),
                tvg_language=_clean(attrs.get("tvg-language")),
                tvg_country=_clean(attrs.get("tvg-country")),
            ))
            pending = None
    return entries
