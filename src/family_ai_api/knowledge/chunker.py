import re
from pathlib import Path

TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "data", "logs"}


def is_indexable(path: Path) -> bool:
    if path.name.startswith("."):
        return False
    if path.name == ".env" or path.name.startswith(".env."):
        return False
    return path.suffix.lower() in TEXT_SUFFIXES


def collect_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if not root.is_symlink() and is_indexable(root) else []

    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts[:-1]
        if any(part in SKIP_DIRS or part.startswith(".") for part in relative_parts):
            continue
        if is_indexable(path):
            files.append(path)
    return files


def chunk_text(text: str, chunk_chars: int = 500, overlap: int = 80) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not text:
        return []

    chunk_chars = max(1, chunk_chars)
    overlap = min(max(0, overlap), chunk_chars - 1)
    chunks: list[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_chars, length)
        if end < length:
            window = text[start:end]
            candidates = [
                window.rfind("\n\n"),
                window.rfind("。"),
                window.rfind("！"),
                window.rfind("？"),
                window.rfind("\n"),
            ]
            cut = max(candidates)
            if cut >= chunk_chars // 2:
                end = start + cut + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(end - overlap, start + 1)

    return chunks


def document_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return path.stem
