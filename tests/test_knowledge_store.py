from pathlib import Path

import pytest

from family_ai_api.knowledge.store import KnowledgeStore


def test_upsert_search_stats_and_delete(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "kb.db")
    try:
        store.upsert_document(
            "a.md", "A", "h1", ["first", "second"], [[1.0, 0.0], [0.0, 1.0]]
        )
        store.upsert_document("b.md", "B", "h2", ["third"], [[1.0, 0.0]])

        results = store.search([1.0, 0.0], top_k=2)
        assert len(results) == 2
        assert results[0].score == pytest.approx(1.0)
        assert {result.source for result in results} == {"a.md", "b.md"}

        stats = store.stats()
        assert stats["documents"] == 2
        assert stats["chunks"] == 3
        assert store.get_document_hash("a.md") == "h1"

        store.upsert_document("a.md", "A2", "h3", ["replacement"], [[0.5, 0.5]])
        assert store.stats()["documents"] == 2
        assert store.stats()["chunks"] == 2
        assert store.get_document_hash("a.md") == "h3"

        assert store.delete_source("b.md") is True
        assert store.delete_source("b.md") is False
        assert store.stats()["documents"] == 1
        assert store.stats()["chunks"] == 1
    finally:
        store.close()


def test_search_empty_store(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "kb.db")
    try:
        assert store.search([1.0, 0.0], top_k=4) == []
    finally:
        store.close()


def test_search_rejects_dimension_mismatch(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "kb.db")
    try:
        store.upsert_document("a.md", "A", "h1", ["first"], [[1.0, 0.0]])
        with pytest.raises(ValueError):
            store.search([1.0, 0.0, 0.0], top_k=1)
    finally:
        store.close()
