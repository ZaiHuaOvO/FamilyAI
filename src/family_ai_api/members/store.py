from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    token_hash TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
"""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Member:
    id: int
    name: str
    role: str
    created_at: str
    revoked_at: str | None = None

    @property
    def revoked(self) -> bool:
        return self.revoked_at is not None


def _row_to_member(row: sqlite3.Row) -> Member:
    return Member(
        id=row["id"],
        name=row["name"],
        role=row["role"],
        created_at=row["created_at"],
        revoked_at=row["revoked_at"],
    )


class MemberStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS count FROM members").fetchone()[
            "count"
        ]

    def get(self, name: str) -> Member | None:
        row = self._conn.execute(
            "SELECT * FROM members WHERE name = ?", (name,)
        ).fetchone()
        return _row_to_member(row) if row is not None else None

    def add(
        self,
        name: str,
        role: str = "member",
        token: str | None = None,
    ) -> tuple[Member, str]:
        name = name.strip()
        if not name:
            raise ValueError("member name must not be empty")
        if role not in {"admin", "member"}:
            raise ValueError("role must be admin or member")

        raw_token = token or secrets.token_urlsafe(32)
        now = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO members (name, token_hash, role, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (name, hash_token(raw_token), role, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("member or token already exists") from exc

        member = self.get(name)
        assert member is not None
        return member, raw_token

    def list(self) -> list[Member]:
        rows = self._conn.execute("SELECT * FROM members ORDER BY id").fetchall()
        return [_row_to_member(row) for row in rows]

    def authenticate(self, token: str) -> Member | None:
        row = self._conn.execute(
            "SELECT * FROM members WHERE token_hash = ? AND revoked_at IS NULL",
            (hash_token(token),),
        ).fetchone()
        return _row_to_member(row) if row is not None else None

    def rotate(self, name: str) -> str | None:
        member = self.get(name)
        if member is None:
            return None
        raw_token = secrets.token_urlsafe(32)
        with self._conn:
            self._conn.execute(
                "UPDATE members SET token_hash = ?, revoked_at = NULL WHERE name = ?",
                (hash_token(raw_token), name),
            )
        return raw_token

    def revoke(self, name: str) -> bool:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE members SET revoked_at = ? "
                "WHERE name = ? AND revoked_at IS NULL",
                (now, name),
            )
            return cursor.rowcount > 0

    def ensure_bootstrap(self, token: str) -> None:
        if not token or self.get("admin") is not None:
            return
        if self.authenticate(token) is not None:
            return
        self.add("admin", "admin", token)
