import sqlite3
from pathlib import Path

import numpy as np
import pytest

from family_ai_api.memory.store import DuplicateMemoryError, MemoryStore


def test_add_get_list_update_delete(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    try:
        memory = store.add("周末优先户外", ["家庭"], "explicit", [1.0, 0.0])
        assert memory.id > 0
        assert memory.content == "周末优先户外"
        assert memory.tags == ["家庭"]
        assert memory.source == "explicit"
        assert memory.owner == "shared"
        assert store.count() == 1
        assert store.get(memory.id) == memory

        with pytest.raises(DuplicateMemoryError):
            store.add("周末优先户外", [], "auto", [1.0, 0.0])

        updated = store.update(
            memory.id,
            content="周末优先户外活动",
            tags=["家庭", "周末"],
            embedding=[0.0, 1.0],
        )
        assert updated is not None
        assert updated.content == "周末优先户外活动"
        assert updated.tags == ["家庭", "周末"]

        tags_only = store.update(memory.id, tags=["家庭"])
        assert tags_only is not None
        assert tags_only.content == "周末优先户外活动"
        assert tags_only.tags == ["家庭"]

        with pytest.raises(ValueError):
            store.update(memory.id, content="没有新向量")

        assert store.delete(memory.id) is True
        assert store.delete(memory.id) is False
        assert store.count() == 0
    finally:
        store.close()


def test_same_content_allowed_per_owner(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    try:
        first = store.add(
            "相同内容", [], "explicit", [1.0, 0.0], owner="1", visibility="private"
        )
        second = store.add(
            "相同内容", [], "explicit", [1.0, 0.0], owner="2", visibility="private"
        )

        with pytest.raises(DuplicateMemoryError):
            store.add(
                "相同内容",
                [],
                "explicit",
                [1.0, 0.0],
                owner="1",
                visibility="private",
            )

        assert [memory.id for memory in store.list(owner="1")] == [first.id]
        assert [memory.id for memory in store.list(owner="2")] == [second.id]
    finally:
        store.close()


def test_legacy_schema_is_migrated(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE memories (
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
        """
    )
    conn.execute(
        "INSERT INTO memories "
        "(content, tags, source, owner, content_hash, created_at, updated_at, embedding) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "legacy",
            "[]",
            "explicit",
            "shared",
            "hash",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
            np.asarray([1.0, 0.0], dtype=np.float32).tobytes(),
        ),
    )
    conn.commit()
    conn.close()

    store = MemoryStore(db_path)
    try:
        memories = store.list()
        assert [memory.content for memory in memories] == ["legacy"]
        assert memories[0].visibility == "shared"
        assert store.search([1.0, 0.0], 1)[0].memory.content == "legacy"
    finally:
        store.close()

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert "memories_old" not in tables
    assert "memories_new" not in tables


def test_search_ranking_and_threshold(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    try:
        store.add("户外", [], "explicit", [1.0, 0.0])
        store.add("电影", [], "explicit", [0.0, 1.0])

        results = store.search([1.0, 0.0], top_k=2, min_score=0.5)

        assert len(results) == 1
        assert results[0].memory.content == "户外"
        assert results[0].score == pytest.approx(1.0)
    finally:
        store.close()


def test_search_empty_and_dimension_mismatch(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    try:
        assert store.search([1.0, 0.0], top_k=2) == []

        store.add("户外", [], "explicit", [1.0, 0.0])
        with pytest.raises(ValueError):
            store.search([1.0, 0.0, 0.0], top_k=2)
    finally:
        store.close()
