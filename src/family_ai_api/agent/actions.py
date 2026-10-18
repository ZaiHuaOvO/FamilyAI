from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class PendingAction:
    id: str
    tool: str
    arguments: dict
    token_key: str
    created_at: str
    expires_at: str


class ActionStore:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._actions: dict[str, PendingAction] = {}

    def create(self, tool: str, arguments: dict, token_key: str) -> PendingAction:
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=self._ttl)
        action = PendingAction(
            id=secrets.token_urlsafe(18),
            tool=tool,
            arguments=dict(arguments),
            token_key=token_key,
            created_at=now.isoformat(timespec="seconds"),
            expires_at=expires.isoformat(timespec="seconds"),
        )
        self._actions[action.id] = action
        return action

    def _expired(self, action: PendingAction) -> bool:
        return datetime.fromisoformat(action.expires_at) <= datetime.now(UTC)

    def get(self, action_id: str, token_key: str) -> PendingAction | None:
        action = self._actions.get(action_id)
        if action is None:
            return None
        if self._expired(action):
            self._actions.pop(action_id, None)
            return None
        if action.token_key != token_key:
            return None
        return action

    def pop(self, action_id: str, token_key: str) -> PendingAction | None:
        action = self.get(action_id, token_key)
        if action is None:
            return None
        return self._actions.pop(action_id, None)

    def cancel(self, action_id: str, token_key: str) -> bool:
        action = self._actions.get(action_id)
        if action is None:
            return False
        if self._expired(action):
            self._actions.pop(action_id, None)
            return False
        if action.token_key != token_key:
            return False
        self._actions.pop(action_id, None)
        return True
