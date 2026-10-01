"""Canonical channel identity: key, display name, and rule-based group.

Design (see project discussion):
- Do NOT trust playlist display names or group-title as identity.
- Compute a canonical key from the name; merge sources that share the key.
- Display name comes from a dictionary when possible.
- Group is assigned by rules (央视 / 卫视 / 其他), not by the source list.
- HD vs non-HD is the same channel (multiple lines), not two channels.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Display dictionary: canonical key → stable Chinese/English label
# ---------------------------------------------------------------------------

CCTV_DISPLAY: dict[str, str] = {
    "cctv-1": "CCTV-1 综合",
    "cctv-2": "CCTV-2 财经",
    "cctv-3": "CCTV-3 综艺",
    "cctv-4": "CCTV-4 中文国际",
    "cctv-5": "CCTV-5 体育",
    "cctv-5-plus": "CCTV-5+",
    "cctv-6": "CCTV-6 电影",
    "cctv-7": "CCTV-7 国防军事",
    "cctv-8": "CCTV-8 电视剧",
    "cctv-9": "CCTV-9 纪录",
    "cctv-10": "CCTV-10 科教",
    "cctv-11": "CCTV-11 戏曲",
    "cctv-12": "CCTV-12 社会与法",
    "cctv-13": "CCTV-13 新闻",
    "cctv-14": "CCTV-14 少儿",
    "cctv-15": "CCTV-15 音乐",
    "cctv-16": "CCTV-16 奥林匹克",
    "cctv-17": "CCTV-17 农业农村",
    "cctv-4k": "CCTV-4K",
}

GROUP_CCTV = "央视"
GROUP_SAT = "卫视"
GROUP_OTHER = "其他"

# Quality / tech suffixes stripped AFTER special channels (CCTV-4K, 5+) are recognized.
_QUALITY_TAIL = re.compile(
    r"(?:"
    r"50\s*FPS|60\s*FPS|"
    r"HEVC|H\.?\s*265|H\.?\s*264|"
    r"蓝光|超清|高清|HDR|FHD|UHD|"
    r"HD|4K"
    r")+$",
    re.IGNORECASE,
)
_BRACKET_NOISE = re.compile(r"[\(\[【（][^\)\]】）]*[\)\]】）]")
_SEPS = re.compile(r"[\s\-_·・.．/／\\|]+")


@dataclass(frozen=True)
class ChannelIdentity:
    """Resolved channel identity for import / export."""

    key: str
    display_name: str
    group: str
    raw: str = ""


def _fullwidth_to_halfwidth(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def pre_clean(name: str | None) -> str:
    """Fullwidth→half, upper Latin, drop separators and bracket noise."""
    if not name:
        return ""
    s = _fullwidth_to_halfwidth(str(name)).replace("\ufeff", "").strip()
    s = _BRACKET_NOISE.sub("", s)
    # Latin to upper for stable CCTV matching; Chinese unchanged.
    s = "".join(ch.upper() if "a" <= ch.lower() <= "z" else ch for ch in s)
    s = s.replace("中央电视台", "CCTV")
    s = s.replace("中央台", "CCTV")
    s = _SEPS.sub("", s)
    return s


def strip_quality_suffixes(text: str) -> str:
    """Remove trailing quality tokens. Call only after special-case channels."""
    s = text
    prev = None
    while prev != s:
        prev = s
        s = _QUALITY_TAIL.sub("", s)
    return s


def _cctv_identity(cleaned: str) -> ChannelIdentity | None:
    """Extract CCTV canonical key. Digits are greedy so CCTV1 ≠ CCTV10."""
    # Independent 4K channel (before generic 4K strip would destroy it).
    if re.fullmatch(r"CCTV4K", cleaned) or re.match(r"^CCTV4K(?!\d)", cleaned):
        return ChannelIdentity("cctv-4k", CCTV_DISPLAY["cctv-4k"], GROUP_CCTV)

    # CCTV5+ / CCTV5PLUS must not become CCTV5.
    m_plus = re.match(r"^CCTV(\d+)(?:\+|PLUS)", cleaned)
    if m_plus:
        num = int(m_plus.group(1))
        key = f"cctv-{num}-plus"
        display = CCTV_DISPLAY.get(key) or f"CCTV-{num}+"
        return ChannelIdentity(key, display, GROUP_CCTV)

    # After quality strip: CCTV1综合HD → CCTV1综合
    body = strip_quality_suffixes(cleaned)
    m = re.match(r"^CCTV(\d+)", body)
    if not m:
        # Embedded form still accepted (e.g. leftover prefix junk rare)
        m = re.search(r"CCTV(\d+)(?:\+|PLUS)?", body)
        if not m:
            return None
        num = int(m.group(1))
        # If original had plus near the number
        plus = bool(re.search(rf"CCTV{num}(?:\+|PLUS)", cleaned))
        key = f"cctv-{num}-plus" if plus else f"cctv-{num}"
        display = CCTV_DISPLAY.get(key) or (f"CCTV-{num}+" if plus else f"CCTV-{num}")
        return ChannelIdentity(key, display, GROUP_CCTV)

    num = int(m.group(1))
    key = f"cctv-{num}"
    display = CCTV_DISPLAY.get(key) or f"CCTV-{num}"
    return ChannelIdentity(key, display, GROUP_CCTV)


def _cctv_named_without_number(cleaned: str) -> ChannelIdentity | None:
    """中央电视台新闻 → CCTV新闻: still 央视; map common names to numbered keys."""
    if not cleaned.startswith("CCTV"):
        return None
    body = strip_quality_suffixes(cleaned)
    rest = body[4:]  # after CCTV
    if not rest or rest[0].isdigit():
        return None
    # Common CCTV branded names without explicit numbers
    named = {
        "新闻": "cctv-13",
        "新闻频道": "cctv-13",
        "综合": "cctv-1",
        "财经": "cctv-2",
        "综艺": "cctv-3",
        "体育": "cctv-5",
        "电影": "cctv-6",
        "电视剧": "cctv-8",
        "纪录": "cctv-9",
        "科教": "cctv-10",
        "戏曲": "cctv-11",
        "少儿": "cctv-14",
        "音乐": "cctv-15",
    }
    for label, key in named.items():
        if rest.startswith(label):
            return ChannelIdentity(
                key, CCTV_DISPLAY.get(key) or f"CCTV-{key.split('-')[1]}", GROUP_CCTV
            )
    # Unknown CCTV-* still groups under 央视
    key = "cctv-" + re.sub(r"[^\w]+", "-", rest.casefold(), flags=re.UNICODE).strip("-")
    return ChannelIdentity(key or "cctv-unknown", f"CCTV {rest}", GROUP_CCTV)


def _satellite_identity(cleaned: str) -> ChannelIdentity | None:
    body = strip_quality_suffixes(cleaned)
    m = re.search(r"(.+卫视)", body)
    if not m:
        return None
    name = m.group(1)
    # Drop trailing 频道 only (avoid stripping 台 from 台卫视 edge cases).
    name = re.sub(r"频道$", "", name)
    if not name.endswith("卫视"):
        return None
    return ChannelIdentity(name, name, GROUP_SAT)


def _other_identity(cleaned: str, raw: str) -> ChannelIdentity:
    body = strip_quality_suffixes(cleaned) or cleaned or "UNKNOWN"
    # Stable key: casefold alphanumeric + CJK
    key = body.casefold()
    key = re.sub(r"[^\w]+", "-", key, flags=re.UNICODE)
    key = re.sub(r"-+", "-", key).strip("-") or "unknown"
    # Prefer a mildly readable display from raw name without quality tails.
    display_src = pre_clean(raw)
    display_src = strip_quality_suffixes(display_src) or body
    display = display_src if display_src else key
    return ChannelIdentity(key, display, GROUP_OTHER)


def resolve_channel(
    *,
    tvg_id: str | None = None,
    tvg_name: str | None = None,
    display_name: str | None = None,
) -> ChannelIdentity:
    """Resolve playlist fields into canonical key, display name, and group.

    Preference order for the *input string*: display_name → tvg_name → tvg_id.
    tvg-id alone is last resort (often reused numeric junk).
    """
    raw = (display_name or tvg_name or tvg_id or "").strip() or "unknown"
    cleaned = pre_clean(raw)
    if not cleaned:
        return ChannelIdentity("unknown", "unknown", GROUP_OTHER, raw)

    for fn in (_cctv_identity, _cctv_named_without_number, _satellite_identity):
        hit = fn(cleaned)
        if hit is not None:
            return ChannelIdentity(hit.key, hit.display_name, hit.group, raw)

    return _other_identity(cleaned, raw)


def channel_id_for(*, tvg_id=None, tvg_name=None, display_name=None) -> str:
    """Backward-compatible: return only the canonical key."""
    return resolve_channel(
        tvg_id=tvg_id, tvg_name=tvg_name, display_name=display_name
    ).key


def rule_group_for_key(key: str, display_name: str | None = None) -> str:
    """Group purely from key / name rules (never from source group-title)."""
    k = (key or "").casefold()
    if k.startswith("cctv-") or k == "cctv-4k":
        return GROUP_CCTV
    if (display_name or key or "").endswith("卫视"):
        return GROUP_SAT
    if k.endswith("卫视") or "卫视" in (display_name or ""):
        return GROUP_SAT
    return GROUP_OTHER


DEFAULT_ALIASES = {
    "cctv-1": {"cctv1", "cctv-1", "cctv 1", "cctv1综合", "中央电视台1", "cctv-1 综合"},
}


def aliases_for(channel_id: str) -> set:
    return DEFAULT_ALIASES.get(channel_id, set())


_GROUP_SORT = {GROUP_CCTV: 0, GROUP_SAT: 1, GROUP_OTHER: 2}


def channel_sort_key(name_or_id: str | None):
    """Stable sort: 央视 by CCTV number, then 卫视, then others.

    Accepts display names (CCTV-3 综艺) or canonical ids (cctv-3).
    CCTV-1, CCTV-2, … CCTV-10 ordered by integer, not lexicographic text.
    """
    text = (name_or_id or "").strip()
    if not text:
        return (9, 9999, 0, "")

    # Prefer parsing as canonical key first (channel id).
    key_l = text.casefold()
    m = re.fullmatch(r"cctv-(\d+)(-plus)?", key_l)
    if m:
        return (0, int(m.group(1)), 1 if m.group(2) else 0, key_l)
    if key_l == "cctv-4k":
        return (0, 4, 2, key_l)

    ident = resolve_channel(display_name=text)
    m = re.fullmatch(r"cctv-(\d+)(-plus)?", ident.key)
    if m:
        return (0, int(m.group(1)), 1 if m.group(2) else 0, ident.key)
    if ident.key == "cctv-4k":
        return (0, 4, 2, ident.key)
    g = _GROUP_SORT.get(ident.group, 2)
    label = ident.display_name or text
    return (g, 0, 0, label)
