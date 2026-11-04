"""Type-contract tests for src.core.security.security_manager."""

from __future__ import annotations

from typing import Any, get_args, get_type_hints

import pytest

from src.core.auth.types import VerifiedJWTPayload
from src.core.security.security_manager import ProductionSecurityManager


@pytest.mark.unit
class TestSecurityManagerJWTTypeContract:
    """Ensure ProductionSecurityManager.verify_token uses VerifiedJWTPayload."""

    def test_verify_token_returns_verified_payload(self) -> None:
        hints = get_type_hints(ProductionSecurityManager.verify_token)
        ret = hints["return"]
        assert VerifiedJWTPayload in get_args(ret), (
            f"verify_token return expected VerifiedJWTPayload | None, got {ret}"
        )

    def test_verify_token_return_is_not_any_dict(self) -> None:
        hints = get_type_hints(ProductionSecurityManager.verify_token)
        ret = hints["return"]
        assert ret is not Any
        assert Any not in get_args(ret)
