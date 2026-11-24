import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from family_ai_api.config import Settings
from family_ai_api.security import require_token


@pytest.mark.asyncio
async def test_non_ascii_token_is_rejected() -> None:
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="é"
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_token(credentials, Settings(api_access_token="test-token"))

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_returns_fingerprint() -> None:
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="test-token"
    )

    fingerprint = await require_token(
        credentials, Settings(api_access_token="test-token")
    )

    assert len(fingerprint) == 16
