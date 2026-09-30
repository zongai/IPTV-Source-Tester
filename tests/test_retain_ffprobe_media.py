"""Resolution from FFprobe must stick until the next FFprobe measurement."""

from types import SimpleNamespace

from app.database.repository import retain_ffprobe_media_fields


class _FakeSession:
    def __init__(self, prev):
        self._prev = prev

    def scalar(self, _stmt):
        return self._prev


def test_retains_previous_resolution_when_current_has_none():
    prev = SimpleNamespace(
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
        fps=25.0,
        bitrate=4_000_000,
        ffprobe_json='{"ok":true}',
    )
    result = {
        "segment_valid": True,
        "playlist_valid": True,
        "height": None,
        "width": None,
        "ttfb": 0.2,
        "download_speed": 8.0,
        "stability": 1.0,
        "score": 70.0,
        "startup_time": 0.2,
    }
    out = retain_ffprobe_media_fields(_FakeSession(prev), source_id=1, result=result)
    assert out["height"] == 1080
    assert out["width"] == 1920
    assert out["video_codec"] == "h264"
    assert out["audio_codec"] == "aac"
    assert out["fps"] == 25.0
    assert out["bitrate"] == 4_000_000
    assert out["ffprobe_json"] == '{"ok":true}'
    # Score should be refreshed with retained height (>= original when height was missing).
    assert out["score"] is not None
    assert out["score"] >= 70.0


def test_does_not_overwrite_new_ffprobe_resolution():
    prev = SimpleNamespace(
        width=1920, height=1080, video_codec="h264", audio_codec="aac",
        fps=25.0, bitrate=4_000_000, ffprobe_json="{}",
    )
    result = {
        "height": 720,
        "width": 1280,
        "video_codec": "hevc",
        "segment_valid": True,
        "score": 85.0,
    }
    out = retain_ffprobe_media_fields(_FakeSession(prev), source_id=1, result=result)
    assert out["height"] == 720
    assert out["width"] == 1280
    assert out["video_codec"] == "hevc"


def test_no_previous_ffprobe_leaves_result_unchanged():
    result = {"height": None, "width": None, "segment_valid": True, "score": 60.0}
    out = retain_ffprobe_media_fields(_FakeSession(None), source_id=1, result=result)
    assert out["height"] is None
    assert out["width"] is None
    assert out["score"] == 60.0
