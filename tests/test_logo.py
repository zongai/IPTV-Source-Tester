from app.exporters.logo import is_broken_logo, logo_filename_candidates, resolve_tvg_logo, tvlogo_url


def test_detects_empty_filename_logo():
    assert is_broken_logo("https://gcore.jsdelivr.net/gh/taksssss/tv/icon/.png")
    assert is_broken_logo("https://example.com/png/.png")
    assert is_broken_logo("")
    assert is_broken_logo(None)
    assert is_broken_logo("https://cdn.example.com/logo.png") is False


def test_cctv_filename_candidates():
    names = logo_filename_candidates("CCTV-1")
    assert "CCTV1.png" in names
    names = logo_filename_candidates("CCTV5+")
    assert "CCTV5+.png" in names
    names = logo_filename_candidates("cctv-5-plus")
    assert "CCTV5+.png" in names


def test_resolve_replaces_broken_logo():
    logo = resolve_tvg_logo(
        "CCTV-1",
        "https://gcore.jsdelivr.net/gh/taksssss/tv/icon/.png",
    )
    assert logo == tvlogo_url("CCTV1.png")
    assert "vircloud/TVLogo" in logo
    assert logo.endswith("CCTV1.png") or "CCTV1.png" in logo


def test_resolve_keeps_valid_logo():
    good = "https://cdn.jsdelivr.net/gh/vircloud/TVLogo@main/湖南卫视.png"
    assert resolve_tvg_logo("湖南卫视", good) == good


def test_hunan_candidate():
    names = logo_filename_candidates("湖南卫视")
    assert "湖南卫视.png" in names
