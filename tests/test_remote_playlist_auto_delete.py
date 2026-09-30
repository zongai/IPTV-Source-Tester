import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.remote_playlist_service import PERMANENT_HTTP_FAILURES, _failure_is_permanent_http


def test_permanent_http_failures_are_auto_delete_candidates():
    assert {401, 403, 404, 410}.issubset(PERMANENT_HTTP_FAILURES)
    for status in (400, 401, 403, 404, 410, 422):
        assert _failure_is_permanent_http(status) is True
    for status in (408, 429, 500, 502, 503, 504):
        assert _failure_is_permanent_http(status) is False


def test_remote_playlist_model_has_failure_tracking():
    from app.database.models import RemotePlaylistDB
    assert "consecutive_failures" in RemotePlaylistDB.__table__.columns
    assert "auto_deleted_at" in RemotePlaylistDB.__table__.columns
