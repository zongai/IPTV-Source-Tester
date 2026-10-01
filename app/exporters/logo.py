"""Resolve channel logos against https://github.com/vircloud/TVLogo.

Only emit CDN URLs for files that exist in the repo catalog
(``tvlogo_catalog.TVLOGO_FILES``). Broken or suspect upstream logos are
replaced; unknown channels without a catalog hit keep a non-broken URL or None.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlparse

from app.exporters.tvlogo_catalog import TVLOGO_FILES

# jsDelivr CDN for root-level PNGs in vircloud/TVLogo.
TVLOGO_CDN_BASE = "https://cdn.jsdelivr.net/gh/vircloud/TVLogo@main"

# Hosts / path patterns that frequently serve empty or wrong icons.
_SUSPECT_LOGO_MARKERS = (
    "taksssss",
    "/tv/icon/",
    "/icon/.png",
    "/png/.png",
    "placeholder",
    "default-logo",
    "no-logo",
    "null.png",
    "undefined.png",
)

_QUALITY_TAIL = re.compile(
    r"[\s_\-]*(?:HD|SD|FHD|UHD|4K|8K|50FPS|60FPS|高清|超清|超高清|标清|蓝光|频道)$",
    re.IGNORECASE,
)
# CCTV-N / CCTV-N+ with optional Chinese program suffix.
_CCTV_FULL = re.compile(
    r"^CCTV[\s\-_]*(\d+)(?:[\s\-_]*(\+|plus))?(?:[\s\-_].*)?$",
    re.IGNORECASE,
)
_CCTV_KEY = re.compile(r"^cctv-(\d+)(?:-(plus))?$", re.IGNORECASE)
# Common program labels after CCTV number (dictionary display names).
_CCTV_PROG = re.compile(
    r"^(CCTV[\s\-_]*\d+(?:[\s\-_]*(?:\+|plus))?)[\s\-_]*"
    r"(?:综合|财经|综艺|中文国际|体育|电影|国防军事|电视剧|纪录|科教|"
    r"戏曲|社会与法|新闻|少儿|音乐|奥林匹克|农业农村).*$",
    re.IGNORECASE,
)


def is_broken_logo(url: str | None) -> bool:
    """True when the logo URL is missing, empty-filename, or clearly invalid."""
    if url is None:
        return True
    text = str(url).strip()
    if not text:
        return True
    if not text.lower().startswith(("http://", "https://")):
        return True
    try:
        path = unquote(urlparse(text).path or "")
    except Exception:
        return True
    if not path or path.endswith("/"):
        return True
    base = path.rsplit("/", 1)[-1]
    if not base or base in {".png", ".jpg", ".jpeg", ".webp", "png", "jpg"}:
        return True
    if base.startswith("."):
        return True
    name, sep, ext = base.rpartition(".")
    if sep and ext.lower() in {"png", "jpg", "jpeg", "webp", "gif"} and not name.strip():
        return True
    low = text.lower()
    if any(m in low for m in ("/icon/.png", "/png/.png", "/.png", "icon/.jpg")):
        return True
    return False


def is_suspect_logo(url: str | None) -> bool:
    """True for known-bad icon CDNs / placeholders (may still have a filename)."""
    if is_broken_logo(url):
        return True
    text = str(url).strip().lower()
    return any(m in text for m in _SUSPECT_LOGO_MARKERS)


def _strip_quality(name: str) -> str:
    s = name.strip()
    prev = None
    while prev != s:
        prev = s
        s = _QUALITY_TAIL.sub("", s).strip()
    return s


def logo_filename_candidates(channel_name: str | None) -> list[str]:
    """Ordered PNG filenames to try against the TVLogo catalog."""
    raw = (channel_name or "").strip()
    if not raw:
        return []

    seeds: list[str] = []
    for s in (raw, _strip_quality(raw)):
        if s and s not in seeds:
            seeds.append(s)

    # Canonical id style: cctv-1 → CCTV1
    for s in list(seeds):
        m = _CCTV_KEY.match(s)
        if m:
            cctv = f"CCTV{m.group(1)}"
            if m.group(2):
                cctv += "+"
            if cctv not in seeds:
                seeds.insert(0, cctv)
        m = _CCTV_FULL.match(s)
        if m:
            cctv = f"CCTV{m.group(1)}"
            if m.group(2):
                cctv += "+"
            if cctv not in seeds:
                seeds.insert(0, cctv)
        # Drop program suffix: CCTV-10 科教 → CCTV-10
        m = _CCTV_PROG.match(s)
        if m:
            base = m.group(1)
            if base not in seeds:
                seeds.append(base)
            m2 = _CCTV_FULL.match(base)
            if m2:
                cctv = f"CCTV{m2.group(1)}"
                if m2.group(2):
                    cctv += "+"
                if cctv not in seeds:
                    seeds.insert(0, cctv)

    # Compact form without separators
    for s in list(seeds):
        compact = re.sub(r"[\s_\-]+", "", s)
        if compact and compact not in seeds:
            seeds.append(compact)
            m = _CCTV_FULL.match(compact) or re.match(
                r"^CCTV(\d+)(\+|plus)?$", compact, re.IGNORECASE
            )
            if m:
                cctv = f"CCTV{m.group(1)}"
                if m.lastindex and m.group(2):
                    cctv += "+"
                if cctv not in seeds:
                    seeds.insert(0, cctv)

    # Special: CCTV4K
    for s in list(seeds):
        if re.search(r"CCTV[\s\-_]*4K", s, re.IGNORECASE):
            if "CCTV4K" not in seeds:
                seeds.insert(0, "CCTV4K")

    out: list[str] = []
    seen: set[str] = set()
    for v in seeds:
        v = v.strip()
        if not v:
            continue
        fn = v if v.lower().endswith(".png") else f"{v}.png"
        if fn not in seen:
            seen.add(fn)
            out.append(fn)
        # Also try without hyphen variants already covered
    return out


def catalog_match(channel_name: str | None) -> str | None:
    """First candidate filename that exists in vircloud/TVLogo, or None."""
    for fn in logo_filename_candidates(channel_name):
        if fn in TVLOGO_FILES:
            return fn
        # Case-insensitive fallback (repo uses mixed Chinese + Latin)
        for real in TVLOGO_FILES:
            if real.lower() == fn.lower():
                return real
    return None


def tvlogo_url(filename: str) -> str:
    encoded = quote(filename, safe="+")
    return f"{TVLOGO_CDN_BASE}/{encoded}"


def resolve_tvg_logo(
    channel_name: str | None,
    current_logo: str | None = None,
    *,
    force: bool = False,
) -> str | None:
    """Return a logo URL verified against the TVLogo catalog when possible.

    Priority:
    1. Catalog match for the channel name (always preferred when broken/suspect/force
       or when current URL is empty).
    2. Keep a non-broken, non-suspect current_logo if no catalog match.
    3. None if nothing usable.
    """
    matched = catalog_match(channel_name)

    needs_fix = force or is_suspect_logo(current_logo)
    if matched and needs_fix:
        return tvlogo_url(matched)

    # Even when current looks "valid", prefer catalog for known channels so
    # players get stable, existing CDN files instead of random dead links.
    if matched and (is_broken_logo(current_logo) or not current_logo):
        return tvlogo_url(matched)

    if matched:
        # Optional: still prefer catalog for consistency (user reported many wrong icons).
        return tvlogo_url(matched)

    if not is_broken_logo(current_logo) and not is_suspect_logo(current_logo):
        return current_logo

    return None if is_broken_logo(current_logo) else current_logo
