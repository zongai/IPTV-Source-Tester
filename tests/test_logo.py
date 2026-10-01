from app.exporters.logo import (
    catalog_match,
    is_broken_logo,
    is_suspect_logo,
    logo_filename_candidates,
    resolve_tvg_logo,
    tvlogo_url,
)
from app.exporters.tvlogo_catalog import TVLOGO_FILES


def test_catalog_has_core_files():
    for name in ("CCTV1.png", "CCTV10.png", "CCTV5+.png", "CCTV4K.png", "湖南卫视.png"):
        assert name in TVLOGO_FILES


def test_detects_empty_filename_logo():
    assert is_broken_logo("https://gcore.jsdelivr.net/gh/taksssss/tv/icon/.png")
    assert is_broken_logo("https://example.com/png/.png")
    assert is_broken_logo("")
    assert is_broken_logo(None)
    assert is_broken_logo("https://cdn.example.com/logo.png") is False


def test_suspect_taksssss():
    assert is_suspect_logo("https://gcore.jsdelivr.net/gh/taksssss/tv/icon/cctv1.png")


def test_cctv_catalog_match():
    assert catalog_match("CCTV-1") == "CCTV1.png"
    assert catalog_match("CCTV-10 科教") == "CCTV10.png"
    assert catalog_match("cctv-5-plus") == "CCTV5+.png"
    assert catalog_match("CCTV-4K") == "CCTV4K.png"
    assert catalog_match("湖南卫视HD") == "湖南卫视.png"


def test_resolve_replaces_broken_and_maps_catalog():
    logo = resolve_tvg_logo(
        "CCTV-1",
        "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/.png",
    )
    assert logo == tvlogo_url("CCTV1.png")


def test_resolve_prefers_catalog_over_random_url():
    logo = resolve_tvg_logo("CCTV-2", "https://cdn.example.com/some/CCTV2.png")
    assert logo == tvlogo_url("CCTV2.png")
