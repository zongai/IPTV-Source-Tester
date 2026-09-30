from app.parser.normalizer import normalize_url, normalize_channel_name

def test_normalize_url():
    assert normalize_url("HTTPS://Example.COM:443/live/test///?token=abc") == "https://example.com/live/test?token=abc"

def test_channel_normalization():
    assert normalize_channel_name("中央电视台1") == "CCTV-1"
    assert normalize_channel_name("CCTV 1") == "CCTV-1"

def test_normalize_url_preserves_encoded_query():
    u = normalize_url('https://Example.com/live/a%2Fb/?token=a%2Fb%26c')
    assert u == 'https://example.com/live/a%2Fb?token=a%2Fb%26c'
