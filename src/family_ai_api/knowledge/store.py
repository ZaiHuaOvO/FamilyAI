import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
"""


@dataclass(frozen=True)
class SearchResult:
    source: str
    title: str
    chunk_index: int
    content: str
    score: float


class KnowledgeStore:
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

    def get_document_hash(self, source: str) -> str | None:
        row = self._conn.execute(
            "SELECT content_hash FROM documents WHERE source = ?", (source,)
        ).fetchone()
        return row["content_hash"] if row is not None else None

    def upsert_document(
        self,
        source: str,
        title: str,
        content_hash: str,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._conn:
            row = self._conn.execute(
                "SELECT id FROM documents WHERE source = ?", (source,)
            ).fetchone()
            if row is not None:
                document_id = row["id"]
                self._conn.execute(
                    "UPDATE documents SET title = ?, content_hash = ?, indexed_at = ? WHERE id = ?",
                    (title, content_hash, now, document_id),
                )
                self._conn.execute(
                    "DELETE FROM chunks WHERE document_id = ?", (document_id,)
                )
            else:
                cursor = self._conn.execute(
                    "INSERT INTO documents (source, title, content_hash, indexed_at) "
                    "VALUES (?, ?, ?, ?)",
                    (source, title, content_hash, now),
                )
                document_id = cursor.lastrowid

            for index, (content, embedding) in enumerate(
                zip(chunks, embeddings, strict=True)
            ):
                vector = np.asarray(embedding, dtype=np.float32).tobytes()
                self._conn.execute(
                    "INSERT INTO chunks (document_id, chunk_index, content, embedding) "
                    "VALUES (?, ?, ?, ?)",
                    (document_id, index, content, vector),
                )

    def delete_source(self, source: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "DELETE FROM documents WHERE source = ?", (source,)
            )
            return cursor.rowcount > 0

    def stats(self) -> dict[str, object]:
        documents = self._conn.execute(
            "SELECT COUNT(*) AS count FROM documents"
        ).fetchone()["count"]
        chunks = self._conn.execute("SELECT COUNT(*) AS count FROM chunks").fetchone()[
            "count"
        ]
        last_indexed_at = self._conn.execute(
            "SELECT MAX(indexed_at) AS value FROM documents"
        ).fetchone()["value"]
        return {
            "documents": documents,
            "chunks": chunks,
            "last_indexed_at": last_indexed_at,
        }

    def search(self, embedding: list[float], top_k: int) -> list[SearchResult]:
        rows = self._conn.execute(
            "SELECT c.content, c.chunk_index, c.embedding, d.source, d.title "
            "FROM chunks c JOIN documents d ON d.id = c.document_id"
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
        best = np.argsort(scores)[::-1][: max(1, top_k)]

        return [
            SearchResult(
                source=rows[index]["source"],
                title=rows[index]["title"],
                chunk_index=rows[index]["chunk_index"],
                content=rows[index]["content"],
                score=float(scores[index]),
            )
            for index in best
        ]
