from pathlib import Path

from family_ai_api.knowledge.chunker import (
    chunk_text,
    collect_files,
    document_title,
    is_indexable,
)


def test_chunk_text_splits_on_paragraph_boundary() -> None:
    text = "A" * 60 + "\n\n" + "B" * 60

    chunks = chunk_text(text, chunk_chars=100, overlap=10)

    assert chunks[0] == "A" * 60
    assert "B" * 60 in chunks[1]


def test_chunk_text_handles_long_text_with_overlap() -> None:
    text = "这是一个用于测试分块的句子。" * 100

    chunks = chunk_text(text, chunk_chars=80, overlap=20)

    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 80 for chunk in chunks)


def test_chunk_text_empty() -> None:
    assert chunk_text("   \n\n  ") == []


def test_chunk_text_does_not_loop_when_overlap_large() -> None:
    chunks = chunk_text("abcdefghij" * 20, chunk_chars=10, overlap=100)

    assert len(chunks) > 1


def test_is_indexable_rules(tmp_path: Path) -> None:
    assert is_indexable(tmp_path / "note.md")
    assert is_indexable(tmp_path / "note.txt")
    assert not is_indexable(tmp_path / "note.pdf")
    assert not is_indexable(tmp_path / ".env")
    assert not is_indexable(tmp_path / ".hidden.md")


def test_collect_files_skips_hidden_and_env(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("B", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "c.md").write_text("C", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"png")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "d.md").write_text("D", encoding="utf-8")

    files = {path.relative_to(tmp_path).as_posix() for path in collect_files(tmp_path)}

    assert files == {"a.md", "sub/b.txt"}


def test_collect_files_skips_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("# Target", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(target)

    files = collect_files(tmp_path)

    assert files == [target]


def test_document_title_uses_heading(tmp_path: Path) -> None:
    path = tmp_path / "doc.md"

    assert document_title(path, "# 我的标题\n正文") == "我的标题"
    assert document_title(path, "没有标题") == "doc"
