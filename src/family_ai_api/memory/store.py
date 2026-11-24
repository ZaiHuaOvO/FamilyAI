from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT 'shared',
    visibility TEXT NOT NULL DEFAULT 'shared',
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    embedding BLOB NOT NULL,
    UNIQUE(owner, content_hash)
);
CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at);
CREATE INDEX IF NOT EXISTS idx_memories_owner ON memories(owner);
"""

REBUILD_SCHEMA = """
CREATE TABLE memories_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT 'shared',
    visibility TEXT NOT NULL DEFAULT 'shared',
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    embedding BLOB NOT NULL,
    UNIQUE(owner, content_hash)
);
"""


class DuplicateMemoryError(Exception):
    pass


@dataclass(frozen=True)
class Memory:
    id: int
    content: str
    tags: list[str]
    source: str
    owner: str
    visibility: str
    created_at: str
    updated_at: str

    @property
    def shared(self) -> bool:
        return self.visibility == "shared"


@dataclass(frozen=True)
class MemorySearchResult:
    memory: Memory
    score: float


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _row_to_memory(row: sqlite3.Row) -> Memory:
    return Memory(
        id=row["id"],
        content=row["content"],
        tags=json.loads(row["tags"]),
        source=row["source"],
        owner=row["owner"],
        visibility=row["visibility"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class MemoryStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _table_exists(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        return row is not None

    def _migrate(self) -> None:
        self._conn.execute("DROP TABLE IF EXISTS memories_new")

        if self._table_exists("memories_old"):
            old_columns = {
                row["name"]
                for row in self._conn.execute(
                    "PRAGMA table_info(memories_old)"
                ).fetchall()
            }
            visibility = (
                "COALESCE(visibility, 'shared')"
                if "visibility" in old_columns
                else "'shared'"
            )
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO memories "
                    "(id, content, tags, source, owner, visibility, content_hash, "
                    "created_at, updated_at, embedding) "
                    "SELECT id, content, tags, source, owner, "
                    f"{visibility}, content_hash, created_at, updated_at, embedding "
                    "FROM memories_old"
                )
                self._conn.execute("DROP TABLE memories_old")

        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(memories)").fetchall()
        }
        if "visibility" not in columns:
            self._conn.execute(
                "ALTER TABLE memories ADD COLUMN visibility TEXT NOT NULL DEFAULT 'shared'"
            )

        needs_rebuild = False
        for index in self._conn.execute("PRAGMA index_list(memories)").fetchall():
            if not index["unique"]:
                continue
            indexed = [
                row["name"]
                for row in self._conn.execute(
                    f"PRAGMA index_info('{index['name']}')"
                ).fetchall()
            ]
            if indexed == ["content_hash"]:
                needs_rebuild = True
                break

        if needs_rebuild:
            with self._conn:
                self._conn.execute("ALTER TABLE memories RENAME TO memories_old")
                self._conn.execute(REBUILD_SCHEMA)
                self._conn.execute(
                    "INSERT INTO memories_new "
                    "(id, content, tags, source, owner, visibility, content_hash, "
                    "created_at, updated_at, embedding) "
                    "SELECT id, content, tags, source, owner, visibility, content_hash, "
                    "created_at, updated_at, embedding FROM memories_old"
                )
                self._conn.execute("DROP TABLE memories_old")
                self._conn.execute("ALTER TABLE memories_new RENAME TO memories")
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memories_updated "
                    "ON memories(updated_at)"
                )
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memories_owner ON memories(owner)"
                )

    def close(self) -> None:
        self._conn.close()

    def add(
        self,
        content: str,
        tags: list[str],
        source: str,
        embedding: list[float],
        owner: str = "shared",
        visibility: str = "shared",
    ) -> Memory:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        vector = np.asarray(embedding, dtype=np.float32).tobytes()
        try:
            with self._conn:
                cursor = self._conn.execute(
                    "INSERT INTO memories "
                    "(content, tags, source, owner, visibility, content_hash, "
                    "created_at, updated_at, embedding) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        content,
                        json.dumps(tags, ensure_ascii=False),
                        source,
                        owner,
                        visibility,
                        content_hash(content),
                        now,
                        now,
                        vector,
                    ),
                )
                memory_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise DuplicateMemoryError from exc

        memory = self.get(memory_id)
        assert memory is not None
        return memory

    def get(self, memory_id: int, owner: str | None = None) -> Memory | None:
        if owner is None:
            row = self._conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM memories WHERE id = ? AND owner = ?",
                (memory_id, owner),
            ).fetchone()
        return _row_to_memory(row) if row is not None else None

    def list(self, limit: int = 50, owner: str | None = None) -> list[Memory]:
        if owner is None:
            rows = self._conn.execute(
                "SELECT * FROM memories ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE owner = ? OR visibility = 'shared' "
                "ORDER BY updated_at DESC, id DESC LIMIT ?",
                (owner, limit),
            ).fetchall()
        return [_row_to_memory(row) for row in rows]

    def update(
        self,
        memory_id: int,
        content: str | None = None,
        tags: list[str] | None = None,
        visibility: str | None = None,
        embedding: list[float] | None = None,
        owner: str | None = None,
    ) -> Memory | None:
        if owner is None:
            existing = self._conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        else:
            existing = self._conn.execute(
                "SELECT * FROM memories WHERE id = ? AND owner = ?",
                (memory_id, owner),
            ).fetchone()
        if existing is None:
            return None

        new_content = content if content is not None else existing["content"]
        new_tags = tags if tags is not None else json.loads(existing["tags"])
        new_visibility = (
            visibility if visibility is not None else existing["visibility"]
        )
        new_hash = content_hash(new_content)
        effective_owner = owner if owner is not None else existing["owner"]

        duplicate = self._conn.execute(
            "SELECT id FROM memories WHERE owner = ? AND content_hash = ? AND id <> ?",
            (effective_owner, new_hash, memory_id),
        ).fetchone()
        if duplicate is not None:
            raise DuplicateMemoryError

        if content is not None and embedding is None:
            raise ValueError("embedding is required when content changes")

        vector = (
            np.asarray(embedding, dtype=np.float32).tobytes()
            if embedding is not None
            else existing["embedding"]
        )
        now = datetime.now(UTC).isoformat(timespec="seconds")

        with self._conn:
            self._conn.execute(
                "UPDATE memories SET content = ?, tags = ?, visibility = ?, "
                "content_hash = ?, updated_at = ?, embedding = ? WHERE id = ?",
                (
                    new_content,
                    json.dumps(new_tags, ensure_ascii=False),
                    new_visibility,
                    new_hash,
                    now,
                    vector,
                    memory_id,
                ),
            )

        return self.get(memory_id)

    def delete(self, memory_id: int, owner: str | None = None) -> bool:
        with self._conn:
            if owner is None:
                cursor = self._conn.execute(
                    "DELETE FROM memories WHERE id = ?", (memory_id,)
                )
            else:
                cursor = self._conn.execute(
                    "DELETE FROM memories WHERE id = ? AND owner = ?",
                    (memory_id, owner),
                )
            return cursor.rowcount > 0

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS count FROM memories").fetchone()[
            "count"
        ]

    def search(
        self,
        embedding: list[float],
        top_k: int,
        min_score: float = 0.0,
        owner: str | None = None,
    ) -> list[MemorySearchResult]:
        if owner is None:
            rows = self._conn.execute("SELECT * FROM memories").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memories WHERE owner = ? OR visibility = 'shared'",
                (owner,),
            ).fetchall()
        if not rows:
            return []

        matrix = np.vstack(
            [np.frombuffer(row["embedding"], dtype=np.float32) for row in rows]
        )
        query = np.asarray(embedding, dtype=np.float32)
        if matrix.shape[1] != query.shape[0]:
            raise ValueError("embedding dimension mismatch")

        matrix_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-12)
        query_norm = query / (np.linalg.norm(query) + 1e-12)
        scores = matrix_norm @ query_norm

        ranked = [
            (float(scores[index]), rows[index])
            for index in np.argsort(scores)[::-1]
            if float(scores[index]) >= min_score
        ]
        return [
            MemorySearchResult(memory=_row_to_memory(row), score=score)
            for score, row in ranked[: max(1, top_k)]
        ]
