from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class RequestLogEntry:
    timestamp: str
    method: str
    path: str
    status: int
    duration_ms: float
    client: str

    def as_dict(self) -> dict:
        return asdict(self)


class RequestLogStore:
    def __init__(self, max_entries: int = 200) -> None:
        self._entries: deque[RequestLogEntry] = deque(maxlen=max_entries)

    def add(self, entry: RequestLogEntry) -> None:
        self._entries.append(entry)

    def recent(self, limit: int = 50) -> list[RequestLogEntry]:
        if limit <= 0:
            return []
        return list(self._entries)[-limit:][::-1]

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")
