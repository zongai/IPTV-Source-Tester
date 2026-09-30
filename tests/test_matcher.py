from app.matcher.channel_matcher import channel_id_for

def test_cctv_aliases_converge():
    assert channel_id_for(tvg_id=None, tvg_name="CCTV1", display_name="") == "cctv-1"
    assert channel_id_for(tvg_id=None, tvg_name="中央电视台1", display_name="") == "cctv-1"

def test_unknown_channel_stays_separate():
    assert channel_id_for(tvg_id=None, tvg_name="Some Channel", display_name="") == "some-channel"


def test_cctv5_and_cctv5_plus_are_distinct():
    assert channel_id_for(tvg_name='CCTV5', display_name='') == 'cctv-5'
    assert channel_id_for(tvg_name='CCTV5+', display_name='') == 'cctv-5-plus'
    assert channel_id_for(tvg_name='CCTV-5+', display_name='') == 'cctv-5-plus'


def test_cctv_sort_is_numeric_and_plus_is_distinct():
    from app.matcher.channel_matcher import channel_sort_key
    names = ['CCTV10', 'CCTV5+', 'CCTV2', 'CCTV1', 'CCTV5']
    assert sorted(names, key=channel_sort_key) == ['CCTV1', 'CCTV2', 'CCTV5', 'CCTV5+', 'CCTV10']


def test_repeated_numeric_tvg_id_does_not_merge_named_channels():
    # tvg-id values are often reused (1, 2, 3...) across unrelated channels.
    assert channel_id_for(tvg_id="1", tvg_name="北京卫视4K", display_name="北京卫视4K") == "北京卫视4k"
    assert channel_id_for(tvg_id="1", tvg_name="IPTV法治", display_name="IPTV法治") == "iptv法治"
    assert channel_id_for(tvg_id="1", tvg_name="CCTV5", display_name="CCTV5") == "cctv-5"


def test_tvg_id_is_last_resort_only():
    assert channel_id_for(tvg_id="1", tvg_name="", display_name="CCTV5+") == "cctv-5-plus"
    assert channel_id_for(tvg_id="1", tvg_name="", display_name="") == "1"
