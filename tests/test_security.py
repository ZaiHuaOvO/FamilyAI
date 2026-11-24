from fastapi.testclient import TestClient

from family_ai_api.config import Settings, get_settings
from family_ai_api.main import app
from family_ai_api.members.store import MemberStore


def build_settings(tmp_path, token: str = "test-token") -> Settings:
    return Settings(
        api_access_token=token,
        members_db_path=str(tmp_path / "members.db"),
    )


def seed_members(tmp_path) -> None:
    store = MemberStore(tmp_path / "members.db")
    try:
        store.add("admin", "admin", "test-token")
        store.add("alice", "member", "alice-token")
    finally:
        store.close()


def test_bootstrap_admin_me_and_member(tmp_path) -> None:
    seed_members(tmp_path)
    settings = build_settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            admin = client.get(
                "/api/v1/me", headers={"Authorization": "Bearer test-token"}
            )
            alice = client.get(
                "/api/v1/me", headers={"Authorization": "Bearer alice-token"}
            )
    finally:
        app.dependency_overrides.clear()

    assert admin.status_code == 200
    assert admin.json()["name"] == "admin"
    assert admin.json()["role"] == "admin"
    assert alice.status_code == 200
    assert alice.json()["name"] == "alice"
    assert alice.json()["role"] == "member"


def test_wrong_and_revoked_tokens_are_rejected(tmp_path) -> None:
    seed_members(tmp_path)
    settings = build_settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            wrong = client.get(
                "/api/v1/me", headers={"Authorization": "Bearer wrong"}
            )
            store = MemberStore(settings.members_db_path)
            try:
                store.revoke("alice")
            finally:
                store.close()
            revoked = client.get(
                "/api/v1/me", headers={"Authorization": "Bearer alice-token"}
            )
    finally:
        app.dependency_overrides.clear()

    assert wrong.status_code == 401
    assert revoked.status_code == 401


def test_admin_only_endpoints(tmp_path) -> None:
    seed_members(tmp_path)
    settings = build_settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            client.get(
                "/api/v1/me", headers={"Authorization": "Bearer test-token"}
            )
            admin_logs = client.get(
                "/api/v1/logs", headers={"Authorization": "Bearer test-token"}
            )
            member_logs = client.get(
                "/api/v1/logs", headers={"Authorization": "Bearer alice-token"}
            )
            member_audit = client.get(
                "/api/v1/agent/audit",
                headers={"Authorization": "Bearer alice-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert admin_logs.status_code == 200
    assert member_logs.status_code == 403
    assert member_audit.status_code == 403
    assert any(
        entry["member_id"] == 1 for entry in admin_logs.json()["entries"]
    )


def test_no_members_and_no_bootstrap_token(tmp_path) -> None:
    settings = Settings(
        api_access_token="",
        members_db_path=str(tmp_path / "members.db"),
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/me", headers={"Authorization": "Bearer anything"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


def test_non_ascii_token_is_not_authenticated(tmp_path) -> None:
    store = MemberStore(tmp_path / "members.db")
    try:
        store.add("admin", "admin", "test-token")
        assert store.authenticate("é") is None
    finally:
        store.close()
