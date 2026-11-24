from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from family_ai_api.security import MemberContext, require_member

router = APIRouter(tags=["me"])


class MeResponse(BaseModel):
    id: int
    name: str
    role: str


@router.get("/me", response_model=MeResponse)
async def me(
    current: Annotated[MemberContext, Depends(require_member)],
) -> MeResponse:
    return MeResponse(
        id=current.member.id,
        name=current.member.name,
        role=current.member.role,
    )
