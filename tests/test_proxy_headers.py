import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from family_ai_api import main
from family_ai_api.config import Settings, get_settings


@pytest.fixture
def proxy_app(monkeypatch, tmp_path):
    settings = Settings(
        api_access_token="test-token",
        auto_memory_enabled=False,
        members_db_path=str(tmp_path / "members.db"),
        memory_db_path=str(tmp_path / "memory.db"),
        forwarded_allow_ips="127.0.0.1,::1",
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    test_app = main.create_app()
    test_app.dependency_overrides[get_settings] = lambda: settings
    yield test_app
    test_app.dependency_overrides.clear()


def test_trusted_loopback_proxy_headers_are_applied(proxy_app) -> None:
    with TestClient(proxy_app, client=("127.0.0.1", 54321)) as client:
        response = client.get(
            "/api/v1/health", headers={"X-Forwarded-For": "100.64.1.2"}
        )
        entries = proxy_app.state.request_log.recent()

    assert response.status_code == 200
    assert entries[0].client == "100.64.1.2"


def test_untrusted_source_cannot_spoof_forwarded_for(proxy_app) -> None:
    with TestClient(proxy_app, client=("192.168.5.30", 54321)) as client:
        response = client.get(
            "/api/v1/health", headers={"X-Forwarded-For": "1.2.3.4"}
        )
        entries = proxy_app.state.request_log.recent()

    assert response.status_code == 200
    assert entries[0].client == "192.168.5.30"


def test_forwarded_for_uses_rightmost_untrusted_address(proxy_app) -> None:
    with TestClient(proxy_app, client=("127.0.0.1", 54321)) as client:
        response = client.get(
            "/api/v1/health",
            headers={"X-Forwarded-For": "1.2.3.4, 100.64.1.2"},
        )
        entries = proxy_app.state.request_log.recent()

    assert response.status_code == 200
    assert entries[0].client == "100.64.1.2"


def test_proxy_middleware_uses_validated_trust_list(proxy_app) -> None:
    middlewares = [
        middleware
        for middleware in proxy_app.user_middleware
        if middleware.cls is ProxyHeadersMiddleware
    ]

    assert len(middlewares) == 1
    assert middlewares[0].kwargs["trusted_hosts"] == ["127.0.0.1", "::1"]
