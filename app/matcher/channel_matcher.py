"""Canonical channel identity: key, display name, and rule-based group.

Design (see project discussion):
- Do NOT trust playlist display names or group-title as identity.
- Compute a canonical key from the name; merge sources that share the key.
- Display name aligns with EPG channel ids from https://epg.zsdc.eu.org/t.xml.gz
  (e.g. CCTV1, 湖南卫视) so players can match programme guide by tvg-id/name.
- Group is assigned by rules (央视 / 卫视 / 其他), not by the source list.
- HD vs non-HD is the same channel (multiple lines), not two channels.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Display dictionary: canonical key → EPG channel id (t.xml.gz)
# ---------------------------------------------------------------------------

CCTV_DISPLAY: dict[str, str] = {
    "cctv-1": "CCTV1",
    "cctv-2": "CCTV2",
    "cctv-3": "CCTV3",
    "cctv-4": "CCTV4",
    "cctv-5": "CCTV5",
    "cctv-5-plus": "CCTV5+",
    "cctv-6": "CCTV6",
    "cctv-7": "CCTV7",
    "cctv-8": "CCTV8",
    "cctv-9": "CCTV9",
    "cctv-10": "CCTV10",
    "cctv-11": "CCTV11",
    "cctv-12": "CCTV12",
    "cctv-13": "CCTV13",
    "cctv-14": "CCTV14",
    "cctv-15": "CCTV15",
    "cctv-16": "CCTV16",
    "cctv-17": "CCTV17",
    "cctv-4k": "CCTV4K",
}

# Non-CCTV names taken from https://epg.zsdc.eu.org/t.xml.gz channel ids.
# Keys are pre_clean() form (upper Latin, no separators) → EPG display id.
EPG_OTHER_BY_CLEAN: dict[str, str] = {
    "4K少儿专区": "4K少儿专区",
    "4K纪实专区": "4K纪实专区",
    "4K视界专区": "4K视界专区",
    "C": "C",
    "CHANNEL[V]": "C",
    "CDTV1": "CDTV1",
    "CDTV2": "CDTV2",
    "CDTV3": "CDTV3",
    "CDTV4": "CDTV4",
    "CDTV5": "CDTV5",
    "CDTV6": "CDTV6",
    "CDTV8": "DTV",
    "CETV1": "CETV1",
    "CETV2": "CETV2",
    "CGTN法语": "CGTN法语",
    "CGTN英语": "CGTN英语",
    "CGTN西班牙语": "CGTN西班牙语",
    "CHC动作电影": "CHC动作电影",
    "CHC家庭影院": "CHC家庭影院",
    "CHC影迷电影": "CHC影迷电影",
    "DTV": "DTV",
    "SCTV2": "SCTV2",
    "SCTV3": "SCTV3",
    "SCTV4": "SCTV4",
    "SCTV5": "SCTV5",
    "SCTV7": "SCTV7",
    "SCTV科教": "SCTV科教",
    "三沙卫视": "三沙卫视",
    "东南卫视": "东南卫视",
    "东方卫视": "东方卫视",
    "东方财经": "东方财经",
    "中国交通": "中国交通",
    "中国天气": "中国天气",
    "乐游": "乐游",
    "书画频道": "书画频道",
    "云南卫视": "云南卫视",
    "优漫卡通": "优漫卡通",
    "全球大片专区": "全球大片专区",
    "兵团卫视": "兵团卫视",
    "内蒙古卫视": "内蒙古卫视",
    "凤凰中文": "凤凰中文",
    "凤凰资讯": "凤凰资讯",
    "动漫秀场": "动漫秀场",
    "北京卫视": "北京卫视",
    "北京纪实科教": "北京纪实科教",
    "华语影院专区": "华语影院专区",
    "卡酷少儿": "卡酷少儿",
    "厦门卫视": "厦门卫视",
    "吉林卫视": "吉林卫视",
    "四川乡村": "四川乡村",
    "四川卫视": "四川卫视",
    "四海钓鱼": "四海钓鱼",
    "天元围棋": "天元围棋",
    "天津卫视": "天津卫视",
    "宁夏卫视": "宁夏卫视",
    "安多卫视": "安多卫视",
    "安徽卫视": "安徽卫视",
    "宝宝动画专区": "宝宝动画专区",
    "家庭理财": "家庭理财",
    "山东卫视": "山东卫视",
    "山东教育卫视": "山东教育卫视",
    "山西卫视": "山西卫视",
    "峨眉电影": "峨眉电影",
    "广东卫视": "广东卫视",
    "广西卫视": "广西卫视",
    "康巴卫视": "康巴卫视",
    "延边卫视": "延边卫视",
    "快乐垂钓": "快乐垂钓",
    "戏曲精选专区": "戏曲精选专区",
    "新疆卫视": "新疆卫视",
    "星光院线专区": "星光院线专区",
    "梨园": "梨园",
    "欢笑剧场": "欢笑剧场",
    "欢笑剧场4K": "欢笑剧场",
    "求索频道": "求索频道",
    "江苏卫视": "江苏卫视",
    "江西卫视": "江西卫视",
    "河北卫视": "河北卫视",
    "河南卫视": "河南卫视",
    "法治天地": "法治天地",
    "浙江卫视": "浙江卫视",
    "海南卫视": "海南卫视",
    "深圳卫视": "深圳卫视",
    "游戏风云": "游戏风云",
    "湖北卫视": "湖北卫视",
    "湖南卫视": "湖南卫视",
    "热播剧场": "热播剧场",
    "热播剧场专区": "热播剧场",
    "环球旅游": "环球旅游",
    "甘肃卫视": "甘肃卫视",
    "百变课堂专区": "百变课堂专区",
    "看天下精选专区": "看天下精选专区",
    "精彩影视": "精彩影视",
    "经典电影": "经典电影",
    "经典电影专区": "经典电影",
    "西藏卫视": "西藏卫视",
    "谍战剧场专区": "谍战剧场专区",
    "财富天下": "财富天下",
    "贵州卫视": "贵州卫视",
    "辽宁卫视": "辽宁卫视",
    "都市剧场": "都市剧场",
    "重庆卫视": "重庆卫视",
    "金色学堂": "金色学堂",
    "金鹰卡通": "金鹰卡通",
    "金鹰纪实": "金鹰纪实",
    "陕西卫视": "陕西卫视",
    "青春动漫专区": "青春动漫专区",
    "青海卫视": "青海卫视",
    "魅力时尚": "魅力时尚",
    "魅力时尚专区": "魅力时尚",
    "黑龙江卫视": "黑龙江卫视",
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
        display = CCTV_DISPLAY.get(key) or f"CCTV{num}+"
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
        display = CCTV_DISPLAY.get(key) or (f"CCTV{num}+" if plus else f"CCTV{num}")
        return ChannelIdentity(key, display, GROUP_CCTV)

    num = int(m.group(1))
    key = f"cctv-{num}"
    display = CCTV_DISPLAY.get(key) or f"CCTV{num}"
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
                key,
                CCTV_DISPLAY.get(key) or f"CCTV{key.split('-')[1]}",
                GROUP_CCTV,
            )
    # Unknown CCTV-* still groups under 央视
    key = "cctv-" + re.sub(r"[^\w]+", "-", rest.casefold(), flags=re.UNICODE).strip("-")
    return ChannelIdentity(key or "cctv-unknown", f"CCTV{rest}", GROUP_CCTV)


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


def _epg_other_hit(cleaned: str) -> str | None:
    """Map cleaned name onto EPG channel id when known."""
    body = strip_quality_suffixes(cleaned) or cleaned
    if not body:
        return None
    hit = EPG_OTHER_BY_CLEAN.get(body)
    if hit:
        return hit
    # Substring: e.g. 联通湖南卫视HD already handled by satellite; for others
    # try exact body after dropping trailing 频道.
    body2 = re.sub(r"频道$", "", body)
    return EPG_OTHER_BY_CLEAN.get(body2)


def _other_identity(cleaned: str, raw: str) -> ChannelIdentity:
    body = strip_quality_suffixes(cleaned) or cleaned or "UNKNOWN"
    epg_name = _epg_other_hit(cleaned)
    if epg_name:
        # Key stable for merge; display is EPG channel id for player matching.
        key = epg_name.casefold()
        key = re.sub(r"[^\w]+", "-", key, flags=re.UNICODE)
        key = re.sub(r"-+", "-", key).strip("-") or "unknown"
        return ChannelIdentity(key, epg_name, GROUP_OTHER)
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
