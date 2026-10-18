from typing import Annotated

from fastapi import APIRouter, Depends

from family_ai_api.config import Settings, get_settings
from family_ai_api.security import require_token

router = APIRouter(tags=["models"])


@router.get("/models", dependencies=[Depends(require_token)])
async def list_models(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    return {"default_model": settings.ai_model, "models": [settings.ai_model]}
