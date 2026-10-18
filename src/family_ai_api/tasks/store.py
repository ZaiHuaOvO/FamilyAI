from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    due_at TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    owner TEXT NOT NULL DEFAULT 'shared',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_at);
"""

UNSET = object()


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    notes: str
    due_at: str | None
    done: bool
    owner: str
    created_at: str
    updated_at: str


def parse_due_at(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _safe_due(value: str | None) -> datetime | None:
    try:
        return parse_due_at(value)
    except ValueError:
        return None


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        notes=row["notes"],
        due_at=row["due_at"],
        done=bool(row["done"]),
        owner=row["owner"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class TaskStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add(self, title: str, notes: str, due_at: str | None) -> Task:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO tasks (title, notes, due_at, done, created_at, updated_at) "
                "VALUES (?, ?, ?, 0, ?, ?)",
                (title, notes, due_at, now, now),
            )
            task_id = cursor.lastrowid
        task = self.get(task_id)
        assert task is not None
        return task

    def get(self, task_id: int) -> Task | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return _row_to_task(row) if row is not None else None

    def list(
        self,
        status: str = "all",
        due: str = "all",
        now: datetime | None = None,
    ) -> list[Task]:
        rows = self._conn.execute("SELECT * FROM tasks").fetchall()
        tasks = [_row_to_task(row) for row in rows]
        now = now or datetime.now().astimezone()

        if status == "open":
            tasks = [task for task in tasks if not task.done]
        elif status == "done":
            tasks = [task for task in tasks if task.done]

        if due in {"today", "overdue"}:
            filtered: list[Task] = []
            for task in tasks:
                if task.done:
                    continue
                due_at = _safe_due(task.due_at)
                if due_at is None:
                    continue
                if (due == "today" and due_at.date() == now.date()) or (
                    due == "overdue" and due_at.date() < now.date()
                ):
                    filtered.append(task)
            tasks = filtered

        if status == "done":
            tasks.sort(key=lambda task: (task.updated_at, task.id), reverse=True)
        else:
            tasks.sort(
                key=lambda task: (
                    task.done,
                    _safe_due(task.due_at) is None,
                    _safe_due(task.due_at) or now,
                    task.created_at,
                    task.id,
                )
            )

        return tasks

    def update(
        self,
        task_id: int,
        title: str | None = None,
        notes: str | None = None,
        due_at: str | None | object = UNSET,
        done: bool | None = None,
    ) -> Task | None:
        existing = self.get(task_id)
        if existing is None:
            return None

        new_title = title if title is not None else existing.title
        new_notes = notes if notes is not None else existing.notes
        new_due = existing.due_at if due_at is UNSET else due_at
        new_done = existing.done if done is None else done
        now = datetime.now(UTC).isoformat(timespec="seconds")

        with self._conn:
            self._conn.execute(
                "UPDATE tasks SET title = ?, notes = ?, due_at = ?, done = ?, "
                "updated_at = ? WHERE id = ?",
                (new_title, new_notes, new_due, int(new_done), now, task_id),
            )
        return self.get(task_id)

    def delete(self, task_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return cursor.rowcount > 0
