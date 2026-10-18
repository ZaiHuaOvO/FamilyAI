from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from family_ai_api.config import Settings, get_settings
from family_ai_api.main import app

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def task_client(tmp_path):
    settings = Settings(
        api_access_token="test-token",
        ai_model="test-model",
        tasks_db_path=str(tmp_path / "tasks.db"),
        auto_memory_enabled=False,
        memory_db_path=str(tmp_path / "memory.db"),
    )
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, settings
    app.dependency_overrides.clear()


def test_task_endpoints_require_token(task_client) -> None:
    client, _ = task_client

    assert client.post("/api/v1/tasks", json={"title": "x"}).status_code == 401
    assert client.get("/api/v1/tasks").status_code == 401
    assert client.patch("/api/v1/tasks/1", json={"done": True}).status_code == 401
    assert client.delete("/api/v1/tasks/1").status_code == 401
    assert client.get("/api/v1/briefing").status_code == 401


def test_task_crud_and_filters(task_client) -> None:
    client, _ = task_client
    now = datetime.now().astimezone()
    today = now.replace(hour=23, minute=0, second=0, microsecond=0).isoformat()
    overdue = (now - timedelta(days=1)).isoformat()

    created_today = client.post(
        "/api/v1/tasks",
        headers=AUTH,
        json={"title": "今日任务", "notes": "备注", "due_at": today},
    )
    assert created_today.status_code == 201
    today_id = created_today.json()["id"]

    created_overdue = client.post(
        "/api/v1/tasks",
        headers=AUTH,
        json={"title": "逾期任务", "due_at": overdue},
    )
    assert created_overdue.status_code == 201
    overdue_id = created_overdue.json()["id"]

    assert len(client.get("/api/v1/tasks", headers=AUTH).json()["entries"]) == 2
    assert [task["id"] for task in client.get("/api/v1/tasks?due=today", headers=AUTH).json()["entries"]] == [today_id]
    assert [task["id"] for task in client.get("/api/v1/tasks?due=overdue", headers=AUTH).json()["entries"]] == [overdue_id]

    updated = client.patch(
        f"/api/v1/tasks/{today_id}", headers=AUTH, json={"done": True}
    )
    assert updated.status_code == 200
    assert updated.json()["done"] is True

    done_entries = client.get("/api/v1/tasks?status=done", headers=AUTH).json()["entries"]
    assert [task["id"] for task in done_entries] == [today_id]

    cleared = client.patch(
        f"/api/v1/tasks/{today_id}", headers=AUTH, json={"due_at": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["due_at"] is None

    deleted = client.delete(f"/api/v1/tasks/{today_id}", headers=AUTH)
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert client.delete(f"/api/v1/tasks/{today_id}", headers=AUTH).status_code == 404


def test_task_validation(task_client) -> None:
    client, _ = task_client

    assert client.post("/api/v1/tasks", headers=AUTH, json={"title": "   "}).status_code == 422
    assert client.post("/api/v1/tasks", headers=AUTH, json={"title": "a" * 201}).status_code == 422
    assert (
        client.post(
            "/api/v1/tasks",
            headers=AUTH,
            json={"title": "x", "notes": "a" * 2001},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/tasks", headers=AUTH, json={"title": "x", "due_at": "bad-date"}
        ).status_code
        == 422
    )
    created = client.post("/api/v1/tasks", headers=AUTH, json={"title": "任务"})
    task_id = created.json()["id"]
    assert client.patch(f"/api/v1/tasks/{task_id}", headers=AUTH, json={}).status_code == 422
    assert client.patch("/api/v1/tasks/999", headers=AUTH, json={"done": True}).status_code == 404


def test_briefing_without_weather(task_client) -> None:
    client, _ = task_client
    now = datetime.now().astimezone()
    today = now.replace(hour=23, minute=0, second=0, microsecond=0).isoformat()
    overdue = (now - timedelta(days=1)).isoformat()

    client.post("/api/v1/tasks", headers=AUTH, json={"title": "今天", "due_at": today})
    client.post("/api/v1/tasks", headers=AUTH, json={"title": "逾期", "due_at": overdue})
    client.post("/api/v1/tasks", headers=AUTH, json={"title": "无日期"})

    response = client.get("/api/v1/briefing", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["counts"] == {"today": 1, "overdue": 1, "open": 3}
    assert [task["title"] for task in body["tasks"]["today"]] == ["今天"]
    assert [task["title"] for task in body["tasks"]["overdue"]] == ["逾期"]
    assert body["weather"] is None
    assert body["weather_configured"] is False


def test_tasks_page_is_public_html(task_client) -> None:
    client, _ = task_client

    response = client.get("/api/v1/tasks/view")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Family AI" in response.text


def test_task_content_not_in_logs(task_client) -> None:
    client, _ = task_client

    response = client.post(
        "/api/v1/tasks", headers=AUTH, json={"title": "private-task-title"}
    )
    assert response.status_code == 201

    logs = client.get("/api/v1/logs?limit=20", headers=AUTH)

    assert logs.status_code == 200
    assert "private-task-title" not in logs.text
    assert "test-token" not in logs.text
