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
    content_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at);
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
    created_at: str
    updated_at: str


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
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add(
        self,
        content: str,
        tags: list[str],
        source: str,
        embedding: list[float],
        owner: str = "shared",
    ) -> Memory:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        vector = np.asarray(embedding, dtype=np.float32).tobytes()
        try:
            with self._conn:
                cursor = self._conn.execute(
                    "INSERT INTO memories "
                    "(content, tags, source, owner, content_hash, created_at, updated_at, embedding) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        content,
                        json.dumps(tags, ensure_ascii=False),
                        source,
                        owner,
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

    def get(self, memory_id: int) -> Memory | None:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return _row_to_memory(row) if row is not None else None

    def recent(self, limit: int = 50) -> list[Memory]:
        rows = self._conn.execute(
            "SELECT * FROM memories ORDER BY updated_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_memory(row) for row in rows]

    def update(
        self,
        memory_id: int,
        content: str | None = None,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> Memory | None:
        existing = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if existing is None:
            return None

        new_content = content if content is not None else existing["content"]
        new_tags = tags if tags is not None else json.loads(existing["tags"])
        new_hash = content_hash(new_content)

        duplicate = self._conn.execute(
            "SELECT id FROM memories WHERE content_hash = ? AND id <> ?",
            (new_hash, memory_id),
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
                "UPDATE memories SET content = ?, tags = ?, content_hash = ?, "
                "updated_at = ?, embedding = ? WHERE id = ?",
                (
                    new_content,
                    json.dumps(new_tags, ensure_ascii=False),
                    new_hash,
                    now,
                    vector,
                    memory_id,
                ),
            )

        return self.get(memory_id)

    def delete(self, memory_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM memories WHERE id = ?", (memory_id,)
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
    ) -> list[MemorySearchResult]:
        rows = self._conn.execute("SELECT * FROM memories").fetchall()
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
