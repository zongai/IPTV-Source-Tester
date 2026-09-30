"""Resolve channel logos from https://github.com/vircloud/TVLogo.

Broken upstream logos often look like:
  https://gcore.jsdelivr.net/gh/taksssss/tv/icon/.png
(empty filename). We rewrite those to vircloud/TVLogo CDN URLs.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlparse

# jsDelivr CDN for the vircloud/TVLogo repo (root-level PNG files).
TVLOGO_CDN_BASE = "https://cdn.jsdelivr.net/gh/vircloud/TVLogo@main"

_QUALITY_SUFFIX_RE = re.compile(
    r"[\s_\-]*(?:HD|SD|FHD|UHD|4K|8K|高清|超清|超高清|标清|频道)$",
    re.IGNORECASE,
)
_CCTV_RE = re.compile(
    r"^CCTV[\s\-_]*(\d+)(?:[\s\-_]*(\+|plus))?$",
    re.IGNORECASE,
)
_CCTV_SLUG_RE = re.compile(
    r"^cctv[\s\-_]*(\d+)(?:[\s\-_]*(plus))?$",
    re.IGNORECASE,
)


def is_broken_logo(url: str | None) -> bool:
    """Return True when the logo URL is missing or has an empty/invalid filename."""
    if url is None:
        return True
    text = str(url).strip()
    if not text:
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
    # Common bad patterns from scrapers / icon CDNs
    if "/icon/.png" in text or "/png/.png" in text or text.endswith("/.png"):
        return True
    return False


def logo_filename_candidates(channel_name: str | None) -> list[str]:
    """Build ordered PNG filename candidates matching vircloud/TVLogo naming.

    Prefer repo-style names first (e.g. CCTV1.png over CCTV-1.png).
    """
    raw = (channel_name or "").strip()
    if not raw:
        return []

    preferred: list[str] = []
    fallback: list[str] = [raw]
    cleaned = _QUALITY_SUFFIX_RE.sub("", raw).strip()
    if cleaned and cleaned not in fallback:
        fallback.append(cleaned)

    def _add_cctv(base: str) -> None:
        m = _CCTV_RE.match(base) or _CCTV_SLUG_RE.match(base)
        if m:
            cctv = f"CCTV{m.group(1)}"
            if m.group(2):
                cctv += "+"
            if cctv not in preferred:
                preferred.append(cctv)
        m2 = re.match(r"^cctv-(\d+)(?:-(plus))?$", base, re.IGNORECASE)
        if m2:
            cctv = f"CCTV{m2.group(1)}"
            if m2.group(2):
                cctv += "+"
            if cctv not in preferred:
                preferred.append(cctv)

    for base in list(fallback):
        _add_cctv(base)
        compact = re.sub(r"[\s_\-]+", "", base)
        if compact and compact not in fallback:
            fallback.append(compact)
            _add_cctv(compact)

    variants = preferred + [v for v in fallback if v not in preferred]
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        v = v.strip()
        if not v:
            continue
        fn = v if v.lower().endswith(".png") else f"{v}.png"
        if fn not in seen:
            seen.add(fn)
            out.append(fn)
    return out


def tvlogo_url(filename: str) -> str:
    """CDN URL for a vircloud/TVLogo file (supports Chinese filenames)."""
    # Encode path segment but keep characters commonly present in the repo.
    encoded = quote(filename, safe="+")
    return f"{TVLOGO_CDN_BASE}/{encoded}"


def resolve_tvg_logo(
    channel_name: str | None,
    current_logo: str | None = None,
    *,
    force: bool = False,
) -> str | None:
    """Return a usable logo URL.

    - If current_logo is valid and force is False, keep it.
    - If broken/missing (or force), map channel_name to vircloud/TVLogo CDN.
    """
    if not force and not is_broken_logo(current_logo):
        return current_logo

    candidates = logo_filename_candidates(channel_name)
    if not candidates:
        return None if is_broken_logo(current_logo) else current_logo
    return tvlogo_url(candidates[0])
