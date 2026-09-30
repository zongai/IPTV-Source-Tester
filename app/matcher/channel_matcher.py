import re
from app.parser.normalizer import normalize_channel_name


def channel_id_for(*, tvg_id=None, tvg_name=None, display_name=None):
    # tvg-id is an EPG identifier, not a reliable channel identity. Many
    # real-world playlists reuse small numeric IDs (1, 2, 3...) across hundreds
    # of channels. Prefer the human channel name and only fall back to tvg-id
    # when both names are absent.
    candidate = display_name or tvg_name or tvg_id or "unknown"
    n = normalize_channel_name(candidate)

    # Known CCTV numbering aliases are deliberately collapsed.
    m = re.fullmatch(r"CCTV-(\d+)(?:-PLUS)?", n)
    if m:
        return f"cctv-{m.group(1)}-plus" if n.endswith("-PLUS") else f"cctv-{m.group(1)}"

    # Do NOT collapse non-Latin names to a shared "unknown" channel.
    # Python's \w is Unicode-aware, so Chinese/Japanese/etc. channel names
    # remain stable and distinct while punctuation is converted to '-'.
    slug = re.sub(r"[^\w-]+", "-", n, flags=re.UNICODE)
    slug = re.sub(r"-+", "-", slug).strip("-").casefold()
    return slug or "unknown"


DEFAULT_ALIASES = {
    "cctv-1": {"cctv1", "cctv-1", "cctv 1", "cctv1综合", "中央电视台1", "cctv-1 综合"},
}


def aliases_for(channel_id):
    return DEFAULT_ALIASES.get(channel_id, set())


def channel_sort_key(name: str):
    """Sort numbered CCTV channels numerically; keep CCTV N and CCTV N+ distinct."""
    n = normalize_channel_name(name)
    m = re.fullmatch(r"CCTV-(\d+)(-PLUS)?", n)
    if m:
        return (0, int(m.group(1)), 1 if m.group(2) else 0, n)
    return (1, n)
