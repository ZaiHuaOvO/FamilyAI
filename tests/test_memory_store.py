from pathlib import Path

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
