import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

from family_ai_api.config import Settings, get_settings
from family_ai_api.knowledge.chunker import chunk_text, collect_files, document_title
from family_ai_api.knowledge.embeddings import EmbeddingError, embed_texts
from family_ai_api.knowledge.store import KnowledgeStore


def _source_name(path: Path, root: Path) -> str:
    if root.is_dir():
        return path.relative_to(root).as_posix()
    return path.name


async def _index_path(
    path: Path,
    settings: Settings,
    store: KnowledgeStore,
) -> tuple[int, int, int]:
    indexed = 0
    skipped = 0
    new_chunks = 0

    for file_path in collect_files(path):
        source = _source_name(file_path, path)
        text = file_path.read_text(encoding="utf-8", errors="replace")
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        if store.get_document_hash(source) == content_hash:
            skipped += 1
            continue

        chunks = chunk_text(text, settings.kb_chunk_chars, settings.kb_chunk_overlap)
        if not chunks:
            skipped += 1
            continue

        embeddings = await embed_texts(chunks, settings)
        store.upsert_document(
            source=source,
            title=document_title(file_path, text),
            content_hash=content_hash,
            chunks=chunks,
            embeddings=embeddings,
        )
        indexed += 1
        new_chunks += len(chunks)
        print(f"indexed: {source} ({len(chunks)} chunks)")

    return indexed, skipped, new_chunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Index Markdown/TXT files into the Family AI knowledge base."
    )
    parser.add_argument("path", type=Path, help="file or directory to index")
    parser.add_argument(
        "--delete", action="store_true", help="delete indexed sources instead of indexing"
    )
    parser.add_argument("--db", type=Path, default=None, help="override database path")
    parser.add_argument("--model", default=None, help="override embedding model")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"path not found: {args.path}", file=sys.stderr)
        return 2

    settings = get_settings()
    if args.model:
        settings = settings.model_copy(update={"embedding_model": args.model})
    db_path = args.db or Path(settings.kb_db_path)

    store = KnowledgeStore(db_path)
    try:
        if args.delete:
            removed = 0
            for file_path in collect_files(args.path):
                source = _source_name(file_path, args.path)
                if store.delete_source(source):
                    removed += 1
                    print(f"deleted: {source}")
            print(f"deleted sources: {removed}")
            return 0

        try:
            indexed, skipped, new_chunks = asyncio.run(
                _index_path(args.path, settings, store)
            )
        except EmbeddingError as exc:
            print(f"embedding failed: {exc}", file=sys.stderr)
            return 1

        stats = store.stats()
        print(
            f"indexed files: {indexed}, skipped: {skipped}, new chunks: {new_chunks}"
        )
        print(
            f"knowledge base: documents={stats['documents']} chunks={stats['chunks']}"
        )
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
