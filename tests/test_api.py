from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_settings


def test_health_and_routes_without_token():
    settings = get_settings()
    settings.api_token = ""
    settings.public_playlist = False

    with TestClient(app) as c:
        assert c.get('/health').json() == {'status': 'ok'}
        assert c.get('/api/system/status').status_code == 200
        assert c.get('/api/channels').status_code == 200
        assert c.post('/api/tests/start').status_code == 200
        assert c.get('/api/playlists/json').status_code == 200
        assert c.get('/api/player/channels').status_code == 200
        assert c.get('/api/playlists/m3u').status_code == 200


def test_routes_require_token_when_configured():
    settings = get_settings()
    settings.api_token = "test-secret-token"
    settings.public_playlist = False

    try:
        with TestClient(app) as c:
            assert c.get('/api/system/status').status_code == 401
            assert c.get('/api/system/status', headers={'Authorization': 'Bearer wrong'}).status_code == 401
            assert c.get('/api/system/status', headers={'Authorization': 'Bearer test-secret-token'}).status_code == 200
            assert c.get('/api/playlists/json').status_code == 401
            assert c.get('/api/playlists/json', headers={'Authorization': 'Bearer test-secret-token'}).status_code == 200
    finally:
        settings.api_token = ""
        settings.public_playlist = False
