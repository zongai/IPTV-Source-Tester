from app.matcher.channel_matcher import (
    channel_id_for,
    channel_sort_key,
    resolve_channel,
    GROUP_CCTV,
    GROUP_SAT,
    GROUP_OTHER,
)


def test_cctv1_variants_same_key():
    variants = [
        "cctv1",
        "cctv-1",
        "CCTV1",
        "CCTV1-综合",
        "CCTV1-综合HD",
        "CCTV-1 综合",
        "中央电视台1",
    ]
    keys = {channel_id_for(display_name=v) for v in variants}
    assert keys == {"cctv-1"}
    for v in variants:
        ident = resolve_channel(display_name=v)
        assert ident.group == GROUP_CCTV
        assert ident.display_name == "CCTV-1 综合"


def test_cctv10_not_merged_with_cctv1():
    for v in ["CCTV10-科教", "CCTV10-科教HD", "CCTV10", "cctv10", "cctv-10"]:
        assert channel_id_for(display_name=v) == "cctv-10"
    assert channel_id_for(display_name="CCTV1") == "cctv-1"


def test_cctv5_and_plus_distinct():
    assert channel_id_for(display_name="CCTV5") == "cctv-5"
    assert channel_id_for(display_name="CCTV5+") == "cctv-5-plus"
    assert channel_id_for(display_name="CCTV-5+") == "cctv-5-plus"


def test_cctv_4k_independent():
    assert channel_id_for(display_name="CCTV-4K") == "cctv-4k"
    assert channel_id_for(display_name="CCTV4K") == "cctv-4k"
    assert channel_id_for(display_name="CCTV4") == "cctv-4"


def test_satellite_group_and_name():
    ident = resolve_channel(display_name="湖南卫视HD")
    assert ident.key == "湖南卫视"
    assert ident.display_name == "湖南卫视"
    assert ident.group == GROUP_SAT


def test_beijing_weishi_4k_is_weishi_not_4k_key():
    # 4K is quality for 卫视, not a separate key
    assert channel_id_for(display_name="北京卫视4K") == "北京卫视"


def test_unknown_channel_stays_separate():
    assert channel_id_for(tvg_name="Some Channel", display_name="") == "somechannel"


def test_sort_numeric():
    names = ["CCTV10", "CCTV5+", "CCTV2", "CCTV1", "CCTV5", "CCTV-3 综艺", "CCTV-13 新闻"]
    assert sorted(names, key=channel_sort_key) == [
        "CCTV1",
        "CCTV2",
        "CCTV-3 综艺",
        "CCTV5",
        "CCTV5+",
        "CCTV10",
        "CCTV-13 新闻",
    ]


def test_sort_by_canonical_id():
    ids = ["cctv-10", "cctv-2", "cctv-1", "cctv-5-plus"]
    assert sorted(ids, key=channel_sort_key) == ["cctv-1", "cctv-2", "cctv-5-plus", "cctv-10"]


def test_tvg_id_not_merge_unrelated():
    a = channel_id_for(tvg_id="1", tvg_name="北京卫视", display_name="北京卫视")
    b = channel_id_for(tvg_id="1", tvg_name="CCTV5", display_name="CCTV5")
    assert a != b
    assert a == "北京卫视"
    assert b == "cctv-5"


def test_other_group():
    ident = resolve_channel(display_name="某地方新闻HD")
    assert ident.group == GROUP_OTHER
