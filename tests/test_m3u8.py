from app.parser.m3u8 import parse_m3u8

def test_hls_parser():
    p = parse_m3u8("#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXT-X-MEDIA-SEQUENCE:10\n#EXTINF:6,\nseg1.ts\n#EXTINF:6,\nseg2.ts\n")
    assert p.is_valid
    assert p.target_duration == 6
    assert p.media_sequence == 10
    assert p.segments == ["seg1.ts", "seg2.ts"]
