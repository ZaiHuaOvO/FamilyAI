from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class AuditEntry:
    timestamp: str
    tool: str
    write: bool
    status: str
    duration_ms: float
    action_id: str | None

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "tool": self.tool,
            "write": self.write,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "action_id": self.action_id,
        }


class AuditStore:
    def __init__(self, max_entries: int = 200) -> None:
        self._entries: deque[AuditEntry] = deque(maxlen=max_entries)

    def add(
        self,
        tool: str,
        write: bool,
        status: str,
        duration_ms: float,
        action_id: str | None = None,
    ) -> None:
        self._entries.append(
            AuditEntry(
                timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
                tool=tool,
                write=write,
                status=status,
                duration_ms=round(duration_ms, 1),
                action_id=action_id,
            )
        )

    def recent(self, limit: int = 50) -> list[AuditEntry]:
        if limit <= 0:
            return []
        return list(self._entries)[-limit:][::-1]
