from datetime import datetime, timezone

from app.utils.timeutil import to_iso, utc_now


def test_to_iso_naive_utc_gets_z():
    dt = datetime(2026, 10, 1, 4, 26, 59)
    assert to_iso(dt) == "2026-10-01T04:26:59Z"


def test_to_iso_aware_converts_to_utc_z():
    dt = datetime(2026, 10, 1, 12, 26, 59, tzinfo=timezone.utc)
    assert to_iso(dt) == "2026-10-01T12:26:59Z"


def test_to_iso_none():
    assert to_iso(None) is None


def test_utc_now_naive():
    n = utc_now()
    assert n.tzinfo is None
