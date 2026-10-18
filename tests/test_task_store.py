from datetime import datetime, timedelta
from pathlib import Path

from family_ai_api.tasks.store import TaskStore, parse_due_at


def test_task_crud_and_filters(tmp_path: Path) -> None:
    now = datetime.now().astimezone()
    today = now.replace(hour=23, minute=0, second=0, microsecond=0).isoformat()
    overdue = (now - timedelta(days=1)).isoformat()

    store = TaskStore(tmp_path / "tasks.db")
    try:
        task_today = store.add("今日任务", "备注", today)
        task_overdue = store.add("逾期任务", "", overdue)
        task_none = store.add("无到期时间", "", None)

        assert store.get(task_today.id) == task_today
        assert len(store.list(status="open")) == 3
        assert [task.id for task in store.list(due="today")] == [task_today.id]
        assert [task.id for task in store.list(due="overdue")] == [task_overdue.id]

        updated = store.update(
            task_overdue.id, title="已完成的逾期任务", done=True
        )
        assert updated is not None
        assert updated.done is True
        assert [task.id for task in store.list(status="done")] == [task_overdue.id]
        assert store.list(due="overdue") == []

        cleared = store.update(task_today.id, due_at=None)
        assert cleared is not None
        assert cleared.due_at is None

        kept = store.update(task_none.id, notes="只改备注")
        assert kept is not None
        assert kept.title == "无到期时间"
        assert kept.notes == "只改备注"

        assert store.delete(task_today.id) is True
        assert store.delete(task_today.id) is False
        assert len(store.list(status="all")) == 2
    finally:
        store.close()


def test_parse_due_at_handles_naive_and_invalid() -> None:
    assert parse_due_at(None) is None
    assert parse_due_at("2026-10-18T10:00:00+08:00") is not None
    assert parse_due_at("2026-10-18T10:00:00").tzinfo is not None

    try:
        parse_due_at("not-a-date")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
