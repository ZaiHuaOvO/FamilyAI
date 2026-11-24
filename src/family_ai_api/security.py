import hashlib
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from family_ai_api.config import Settings, get_settings
from family_ai_api.members.store import Member, MemberStore

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class MemberContext:
    member: Member
    token_key: str


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


async def require_member(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MemberContext:
    store = MemberStore(settings.members_db_path)
    try:
        store.ensure_bootstrap(settings.api_access_token)
        if store.count() == 0:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="service authentication is not configured",
            )

        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized",
                headers={"WWW-Authenticate": "Bearer"},
            )

        member = store.authenticate(credentials.credentials)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token_key = token_fingerprint(credentials.credentials)
    finally:
        store.close()

    request.state.member_id = member.id
    request.state.member_name = member.name
    return MemberContext(member=member, token_key=token_key)


async def require_admin(
    current: Annotated[MemberContext, Depends(require_member)],
) -> MemberContext:
    if current.member.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin access required",
        )
    return current
