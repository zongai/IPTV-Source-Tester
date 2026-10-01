from app.parser.normalizer import (
    infer_default_group,
    normalize_url,
    normalize_channel_name,
)


def test_normalize_url():
    assert (
        normalize_url("HTTPS://Example.COM:443/live/test///?token=abc")
        == "https://example.com/live/test?token=abc"
    )


def test_channel_normalization():
    assert normalize_channel_name("中央电视台1") == "CCTV1"
    assert normalize_channel_name("CCTV 1") == "CCTV1"
    assert normalize_channel_name("CCTV5+") == "CCTV5+"


def test_normalize_url_preserves_encoded_query():
    u = normalize_url("https://Example.com/live/a%2Fb/?token=a%2Fb%26c")
    assert u == "https://example.com/live/a%2Fb?token=a%2Fb%26c"


def test_infer_default_group_rules():
    assert infer_default_group("CCTV-1 综合") == "央视"
    assert infer_default_group("cctv5+") == "央视"
    assert infer_default_group("中央电视台新闻") == "央视"
    assert infer_default_group("湖南卫视") == "卫视"
    assert infer_default_group("东方卫视高清") == "卫视"
    assert infer_default_group("地方台") == "其他"
