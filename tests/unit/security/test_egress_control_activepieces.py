"""Unit test: EgressController wired into ActivePieces client."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.activepieces.client import ActivePiecesClient
from src.core.activepieces.verbinding import ApVerbinding
from src.core.exceptions.exceptions import EgressBlockedError
from src.core.security.egress_control import (
    EgressController,
    EgressDecision,
    EgressResult,
)


class TestActivePiecesEgressControl:
    """Verify ActivePieces client respects egress policy."""

    @pytest.fixture
    def mock_egress_controller(self):
        controller = MagicMock(spec=EgressController)
        controller.validate_request = AsyncMock()
        return controller

    @pytest.fixture
    def verbinding(self):
        return ApVerbinding(
            tenant_id=7,
            base_url="https://ap.example.com/api",
            email="test@example.com",
            wachtwoord="testpass123",
            project_id="proj-7",
        )

    @pytest.mark.asyncio
    async def test_blocked_domain_raises_egress_blocked_error(
        self, mock_egress_controller, verbinding, monkeypatch
    ):
        """ActivePieces request to blocked domain raises EgressBlockedError."""
        monkeypatch.setenv("FEATURE_FLAG_EGRESS_CONTROL", "true")

        mock_egress_controller.validate_request.return_value = EgressResult(
            decision=EgressDecision.BLOCK,
            reason="Domain not in allowlist",
        )

        client = ActivePiecesClient(verbinding, egress_controller=mock_egress_controller)

        with pytest.raises(EgressBlockedError) as exc_info:
            await client._check_egress("https://evil.com/api/test")

        assert "evil.com" in str(exc_info.value)
        assert "Domain not in allowlist" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_allowed_domain_passes_egress_check(
        self, mock_egress_controller, verbinding, monkeypatch
    ):
        """ActivePieces request to allowed domain passes egress check."""
        monkeypatch.setenv("FEATURE_FLAG_EGRESS_CONTROL", "true")

        mock_egress_controller.validate_request.return_value = EgressResult(
            decision=EgressDecision.ALLOW,
            resolved_ip="1.2.3.4",
        )

        client = ActivePiecesClient(verbinding, egress_controller=mock_egress_controller)

        # Should not raise
        await client._check_egress("https://ap.example.com/api/test")

        mock_egress_controller.validate_request.assert_called_once()
        call_kwargs = mock_egress_controller.validate_request.call_args[1]
        assert call_kwargs["tenant_id"] == 0
        assert "ap.example.com" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_feature_flag_disabled_skips_egress_check(
        self, mock_egress_controller, verbinding, monkeypatch
    ):
        """When feature flag is off, egress check is skipped entirely."""
        monkeypatch.setenv("FEATURE_FLAG_EGRESS_CONTROL", "false")

        client = ActivePiecesClient(verbinding, egress_controller=mock_egress_controller)

        await client._check_egress("https://any-domain.com/api")

        mock_egress_controller.validate_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_egress_controller_skips_check(self, verbinding, monkeypatch):
        """When no egress controller is provided, check is skipped."""
        monkeypatch.setenv("FEATURE_FLAG_EGRESS_CONTROL", "true")

        client = ActivePiecesClient(verbinding, egress_controller=None)

        await client._check_egress("https://any-domain.com/api")
