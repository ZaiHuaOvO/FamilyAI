from family_ai_api.agent.actions import ActionStore
from family_ai_api.agent.audit import AuditStore


def test_action_lifecycle_and_token_binding() -> None:
    store = ActionStore(ttl_seconds=300)

    action = store.create("create_task", {"title": "买菜"}, "token-a")

    assert store.get(action.id, "token-a") == action
    assert store.get(action.id, "token-b") is None
    assert store.pop(action.id, "token-b") is None
    assert store.pop(action.id, "token-a") == action
    assert store.pop(action.id, "token-a") is None


def test_action_cancel_and_expiry() -> None:
    store = ActionStore(ttl_seconds=300)
    action = store.create("create_task", {"title": "买菜"}, "token-a")

    assert store.cancel(action.id, "token-b") is False
    assert store.cancel(action.id, "token-a") is True
    assert store.cancel(action.id, "token-a") is False

    expired_store = ActionStore(ttl_seconds=-1)
    expired = expired_store.create("create_task", {"title": "买菜"}, "token-a")
    assert expired_store.get(expired.id, "token-a") is None
    assert expired_store.pop(expired.id, "token-a") is None


def test_audit_store_records_metadata_only() -> None:
    store = AuditStore(max_entries=2)

    store.add("get_briefing", False, "ok", 12.34)
    store.add("create_task", True, "ok", 5.0, action_id="abc")

    entries = store.recent(10)

    assert [entry.tool for entry in entries] == ["create_task", "get_briefing"]
    assert entries[0].write is True
    assert entries[0].action_id == "abc"
    assert "title" not in entries[0].as_dict()
    assert "arguments" not in entries[0].as_dict()
