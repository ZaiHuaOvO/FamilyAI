import time
from collections import deque


class SlidingWindowRateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self._limit = limit_per_minute
        self._events: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        events = self._events.setdefault(key, deque())
        while events and now - events[0] >= 60.0:
            events.popleft()
        if len(events) >= self._limit:
            return False
        events.append(now)
        return True
