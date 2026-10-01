from app.exporters.logo import catalog_match, is_broken_logo, resolve_tvg_logo, tvlogo_url
from app.exporters.tvlogo_catalog import TVLOGO_FILES
from app.matcher.channel_matcher import resolve_channel


def test_catalog_core():
    for name in ("CCTV1.png", "CCTV10.png", "CCTV5+.png", "湖南卫视.png"):
        assert name in TVLOGO_FILES


def test_broken():
    assert is_broken_logo("https://gcore.jsdelivr.net/gh/taksssss/tv/icon/.png")


def test_match_via_canonical_key():
    assert catalog_match("酒店CCTV1高清", channel_id="cctv-1") == "CCTV1.png"
    assert catalog_match(channel_id="cctv-10") == "CCTV10.png"
    assert catalog_match("广西联通·湖南卫视", channel_id="广西联通湖南卫视") == "湖南卫视.png"


def test_identity_pipeline():
    for raw in ("酒店CCTV1高清", "CCTV-1 综合", "CCTV10-科教HD", "CCTV5+"):
        ident = resolve_channel(display_name=raw)
        logo = resolve_tvg_logo(ident.display_name, None, channel_id=ident.key)
        assert logo and "vircloud/TVLogo" in logo
