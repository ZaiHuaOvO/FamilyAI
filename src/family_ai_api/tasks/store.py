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
    shared INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_at);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner);
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
    shared: bool
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
        shared=bool(row["shared"]),
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
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "shared" not in columns:
            self._conn.execute(
                "ALTER TABLE tasks ADD COLUMN shared INTEGER NOT NULL DEFAULT 0"
            )
            self._conn.execute(
                "UPDATE tasks SET shared = 1 WHERE owner = 'shared'"
            )

    def close(self) -> None:
        self._conn.close()

    def add(
        self,
        title: str,
        notes: str,
        due_at: str | None,
        owner: str = "shared",
        shared: bool = True,
    ) -> Task:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO tasks "
                "(title, notes, due_at, done, owner, shared, created_at, updated_at) "
                "VALUES (?, ?, ?, 0, ?, ?, ?, ?)",
                (title, notes, due_at, owner, int(shared), now, now),
            )
            task_id = cursor.lastrowid
        task = self.get(task_id)
        assert task is not None
        return task

    def get(self, task_id: int, owner: str | None = None) -> Task | None:
        if owner is None:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ? AND owner = ?",
                (task_id, owner),
            ).fetchone()
        return _row_to_task(row) if row is not None else None

    def list(
        self,
        status: str = "all",
        due: str = "all",
        now: datetime | None = None,
        owner: str | None = None,
    ) -> list[Task]:
        if owner is None:
            rows = self._conn.execute("SELECT * FROM tasks").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE owner = ? OR shared = 1", (owner,)
            ).fetchall()

        tasks = [_row_to_task(row) for row in rows]
        now = (now or datetime.now().astimezone()).astimezone()

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
                local_date = due_at.astimezone().date()
                if (due == "today" and local_date == now.date()) or (
                    due == "overdue" and local_date < now.date()
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
        shared: bool | None = None,
        owner: str | None = None,
    ) -> Task | None:
        existing = self.get(task_id, owner)
        if existing is None:
            return None

        new_title = title if title is not None else existing.title
        new_notes = notes if notes is not None else existing.notes
        new_due = existing.due_at if due_at is UNSET else due_at
        new_done = existing.done if done is None else done
        new_shared = existing.shared if shared is None else shared
        now = datetime.now(UTC).isoformat(timespec="seconds")

        with self._conn:
            self._conn.execute(
                "UPDATE tasks SET title = ?, notes = ?, due_at = ?, done = ?, "
                "shared = ?, updated_at = ? WHERE id = ?",
                (
                    new_title,
                    new_notes,
                    new_due,
                    int(new_done),
                    int(new_shared),
                    now,
                    task_id,
                ),
            )
        return self.get(task_id)

    def delete(self, task_id: int, owner: str | None = None) -> bool:
        with self._conn:
            if owner is None:
                cursor = self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            else:
                cursor = self._conn.execute(
                    "DELETE FROM tasks WHERE id = ? AND owner = ?",
                    (task_id, owner),
                )
            return cursor.rowcount > 0
