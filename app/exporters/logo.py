"""Resolve channel logos against https://github.com/vircloud/TVLogo.

Coupled to channel identity: prefer canonical key (cctv-1) and dictionary
display name, then messy raw titles. Only emit CDN URLs for files present in
``tvlogo_catalog.TVLOGO_FILES``.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlparse

from app.exporters.tvlogo_catalog import TVLOGO_FILES

TVLOGO_CDN_BASE = "https://cdn.jsdelivr.net/gh/vircloud/TVLogo@main"

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
_CCTV_KEY = re.compile(r"^cctv-(\d+)(?:-(plus))?$", re.IGNORECASE)
_CCTV_FULL = re.compile(
    r"CCTV[\s\-_]*(\d+)(?:[\s\-_]*(\+|plus))?",
    re.IGNORECASE,
)
_CCTV_4K = re.compile(r"CCTV[\s\-_]*4K", re.IGNORECASE)
_WEISHI = re.compile(r"([\u4e00-\u9fff]{1,8}卫视)")


def is_broken_logo(url: str | None) -> bool:
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


def _cctv_repo_name(num: str, plus: bool = False) -> str:
    return f"CCTV{int(num)}" + ("+" if plus else "")


def logo_filename_candidates(
    channel_name: str | None = None,
    *,
    channel_id: str | None = None,
) -> list[str]:
    """Ordered PNG names to try against the TVLogo catalog.

    Prefer canonical channel id (cctv-1 → CCTV1.png), then display/raw names,
    including CCTV/卫视 embedded inside noisy titles.
    """
    seeds: list[str] = []

    def add(s: str | None) -> None:
        if not s:
            return
        s = str(s).strip()
        if s and s not in seeds:
            seeds.append(s)

    add(channel_id)
    add(channel_name)

    for s in list(seeds):
        add(_strip_quality(s))

    preferred: list[str] = []

    def prefer(fn_base: str) -> None:
        if fn_base and fn_base not in preferred:
            preferred.append(fn_base)

    for s in list(seeds):
        m = _CCTV_KEY.match(s)
        if m:
            prefer(_cctv_repo_name(m.group(1), bool(m.group(2))))
        if _CCTV_4K.search(s):
            prefer("CCTV4K")
        for m in _CCTV_FULL.finditer(s):
            prefer(_cctv_repo_name(m.group(1), bool(m.group(2))))
        for m in _WEISHI.finditer(s):
            prefer(m.group(1))
        compact = re.sub(r"[\s_\-]+", "", s)
        if compact and compact != s:
            add(compact)
            m = _CCTV_FULL.search(compact)
            if m:
                prefer(_cctv_repo_name(m.group(1), bool(m.group(2))))

    for s in list(seeds):
        if "卫视" not in s:
            continue
        for real in TVLOGO_FILES:
            if not real.endswith("卫视.png"):
                continue
            label = real[: -len(".png")]
            if label and label in s:
                prefer(label)

    variants = preferred + [v for v in seeds if v not in preferred]
    out: list[str] = []
    seen: set[str] = set()
    for v in variants:
        v = v.strip()
        if not v:
            continue
        fn = v if v.lower().endswith(".png") else f"{v}.png"
        if fn not in seen:
            seen.add(fn)
            out.append(fn)
    return out


def catalog_match(
    channel_name: str | None = None,
    *,
    channel_id: str | None = None,
) -> str | None:
    lower_map = None
    for fn in logo_filename_candidates(channel_name, channel_id=channel_id):
        if fn in TVLOGO_FILES:
            return fn
        if lower_map is None:
            lower_map = {x.lower(): x for x in TVLOGO_FILES}
        real = lower_map.get(fn.lower())
        if real:
            return real
    return None


def tvlogo_url(filename: str) -> str:
    return f"{TVLOGO_CDN_BASE}/{quote(filename, safe='+')}"


def resolve_tvg_logo(
    channel_name: str | None,
    current_logo: str | None = None,
    *,
    channel_id: str | None = None,
    force: bool = False,
) -> str | None:
    """Resolve logo using channel identity + TVLogo catalog.

    When the channel maps to a catalog file, always use that CDN URL.
    Otherwise keep a non-broken, non-suspect current URL.
    """
    matched = catalog_match(channel_name, channel_id=channel_id)
    if matched:
        return tvlogo_url(matched)

    if force or is_suspect_logo(current_logo) or is_broken_logo(current_logo):
        return None

    return current_logo
