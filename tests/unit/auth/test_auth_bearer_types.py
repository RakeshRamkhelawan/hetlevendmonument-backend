"""Type-contract tests for src.core.auth.auth_bearer."""

from __future__ import annotations

from typing import Any, get_args, get_type_hints

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_bearer import _extract_email, get_current_user
from src.core.auth.auth_service import UserResponse
from src.core.auth.types import VerifiedJWTPayload


@pytest.mark.unit
class TestAuthBearerTypeContract:
    """Ensure auth_bearer uses AsyncSession and concrete payload/user types."""

    def test_get_current_user_db_is_async_session(self) -> None:
        hints = get_type_hints(get_current_user)
        assert hints["db"] is AsyncSession, (
            f"get_current_user db expected AsyncSession, got {hints['db']}"
        )

    def test_get_current_user_returns_user_response(self) -> None:
        hints = get_type_hints(get_current_user)
        ret = hints["return"]
        assert ret is UserResponse, f"get_current_user return expected UserResponse, got {ret}"

    def test_get_current_user_return_is_not_any(self) -> None:
        hints = get_type_hints(get_current_user)
        assert hints["return"] is not Any

    def test_extract_email_uses_verified_payload(self) -> None:
        hints = get_type_hints(_extract_email)
        assert hints["payload"] is VerifiedJWTPayload, (
            f"_extract_email payload expected VerifiedJWTPayload, got {hints['payload']}"
        )

    def test_extract_email_rejects_non_string_values(self) -> None:
        payload = VerifiedJWTPayload(sub=123, tenant_id=1)  # type: ignore[typeddict-item]
        assert _extract_email(payload) is None
