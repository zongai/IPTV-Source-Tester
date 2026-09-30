"""Source auto-delete: consecutive failures AND failure streak age."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.database.repository import _consecutive_validated_failures, maybe_auto_delete_failed_source


def _row(valid, days_ago):
    return SimpleNamespace(
        segment_valid=valid,
        tested_at=datetime.utcnow() - timedelta(days=days_ago),
    )


class _ScalarSession:
    """Minimal session stub: scalar() returns next from a queue of results."""

    def __init__(self, rows, source=None, channel=None):
        self.rows = rows
        self.source = source
        self.channel = channel
        self.deleted = []
        self.executed = []

    def scalars(self, _stmt):
        return self

    def all(self):
        return self.rows

    def scalar(self, _stmt):
        # used for remaining source check after delete → None means empty channel
        return None

    def get(self, model, key):
        name = getattr(model, "__name__", str(model))
        if "Source" in name:
            return self.source
        if "Channel" in name:
            return self.channel
        return None

    def execute(self, stmt):
        self.executed.append(stmt)
        return None

    def delete(self, obj):
        self.deleted.append(obj)

    def flush(self):
        pass


def test_consecutive_counts_only_trailing_failures():
    rows = [
        _row(False, 0),
        _row(False, 1),
        _row(False, 2),
        _row(True, 3),  # success breaks streak
        _row(False, 4),
    ]
    session = _ScalarSession(rows)
    count, start = _consecutive_validated_failures(session, source_id=1)
    assert count == 3
    assert start is not None


def test_no_delete_when_failures_below_threshold():
    source = SimpleNamespace(id=1, channel_id="cctv-1", url="http://x")
    rows = [_row(False, d) for d in range(4)]  # only 4 failures
    session = _ScalarSession(rows, source=source)
    with patch("app.database.repository.get_settings") as gs:
        gs.return_value = SimpleNamespace(
            source_auto_delete_failures=5,
            source_auto_delete_days=5,
        )
        assert maybe_auto_delete_failed_source(session, 1) is None


def test_no_delete_when_streak_too_short():
    source = SimpleNamespace(id=1, channel_id="cctv-1", url="http://x")
    # 5 failures but only over 2 days
    rows = [_row(False, d) for d in (0, 0.5, 1, 1.5, 2)]
    session = _ScalarSession(rows, source=source)
    with patch("app.database.repository.get_settings") as gs:
        gs.return_value = SimpleNamespace(
            source_auto_delete_failures=5,
            source_auto_delete_days=5,
        )
        assert maybe_auto_delete_failed_source(session, 1) is None


def test_deletes_when_both_thresholds_met():
    source = SimpleNamespace(id=7, channel_id="cctv-1", url="http://example/live.m3u8")
    channel = SimpleNamespace(id="cctv-1")
    rows = [_row(False, d) for d in (0, 2, 4, 6, 8)]  # 5 failures, 8 days span
    session = _ScalarSession(rows, source=source, channel=channel)
    with patch("app.database.repository.get_settings") as gs:
        gs.return_value = SimpleNamespace(
            source_auto_delete_failures=5,
            source_auto_delete_days=5,
        )
        summary = maybe_auto_delete_failed_source(session, 7)
    assert summary is not None
    assert summary["deleted"] is True
    assert summary["source_id"] == 7
    assert summary["consecutive_failures"] == 5
    assert source in session.deleted
    assert channel in session.deleted
