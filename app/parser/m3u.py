import re
from app.models.playlist import PlaylistEntry
from app.parser.normalizer import normalize_url
from urllib.parse import urljoin

KNOWN = {"tvg-id","tvg-name","tvg-logo","group-title","tvg-language","tvg-country","tvg-shift","radio"}
_ATTR_RE = re.compile(r'([\w-]+)=(?:"([^"]*)"|([^\s]+))')


def _clean(value):
    return (value or "").replace("\ufeff", "").strip()


def _parse_extinf(line):
    attrs = {m.group(1): _clean(m.group(2) if m.group(2) is not None else m.group(3)) for m in _ATTR_RE.finditer(line)}
    name = _clean(line.split(",", 1)[1] if "," in line else "")
    return attrs, name


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
            pending[0]["__vlcopt__" + key.strip()] = _clean(value)
        elif line.startswith("#EXTHTTP:") and pending:
            payload = line.split(":", 1)[1]
            key, _, value = payload.partition("=")
            pending[0]["__exthttp__" + key.strip()] = _clean(value)
        elif not line.startswith("#") and pending:
            attrs, name, raw = pending
            headers = {}
            for k, v in attrs.items():
                if k.startswith("__") and any(x in k.lower() for x in ("user-agent","referrer","referer","origin","cookie","authorization")):
                    headers[k.split("__", 2)[-1].lower()] = _clean(v)
            entries.append(PlaylistEntry(
                name=_clean(name), url=normalize_url(urljoin(base_url, line) if base_url else line), attributes={k:_clean(v) for k,v in attrs.items()},
                unknown_attributes={k:v for k,v in attrs.items() if k not in KNOWN},
                headers=headers, raw_extinf=raw,
                group=_clean(attrs.get("group-title")), tvg_id=_clean(attrs.get("tvg-id")),
                tvg_name=_clean(attrs.get("tvg-name")), tvg_logo=_clean(attrs.get("tvg-logo")),
                tvg_language=_clean(attrs.get("tvg-language")), tvg_country=_clean(attrs.get("tvg-country")),
            ))
            pending = None
    return entries
