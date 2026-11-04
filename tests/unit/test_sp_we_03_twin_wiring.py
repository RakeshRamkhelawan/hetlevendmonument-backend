"""SP-WE-03: twin_service wiring + consent gate tests."""

import inspect

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.unit
class TestTwinServiceWiring:
    def test_twin_service_in_build_copilot_service_source(self) -> None:
        from src.core.copilot import dependencies

        source = inspect.getsource(dependencies._build_copilot_service)
        assert "twin_service" in source

    def test_copilot_service_constructor_accepts_twin_service(self) -> None:
        from src.core.copilot.service import CopilotService

        sig = inspect.signature(CopilotService.__init__)
        assert "twin_service" in sig.parameters


@pytest.mark.unit
class TestConsentGateAdapter:
    async def test_has_consent_calls_consent_manager(self) -> None:
        from src.core.copilot.council.factory import _ConsentGateAdapter
        from src.core.learning.consent.consent_manager import ConsentCategories

        mock_manager = AsyncMock()
        mock_manager.get_consent_categories.return_value = ConsentCategories(
            behavior_tracking=False,
            profile_aggregation=False,
            ai_interventions=False,
            cross_session_memory=True,
        )

        adapter = _ConsentGateAdapter(consent_manager=mock_manager)
        result = await adapter.has_consent(user_id=42, tenant_id=1)

        assert mock_manager.get_consent_categories.called
        assert result is True

    async def test_has_consent_returns_false_when_consent_denied(self) -> None:
        from src.core.copilot.council.factory import _ConsentGateAdapter
        from src.core.learning.consent.consent_manager import ConsentCategories

        mock_manager = AsyncMock()
        mock_manager.get_consent_categories.return_value = ConsentCategories(
            behavior_tracking=True,
            profile_aggregation=True,
            ai_interventions=True,
            cross_session_memory=False,
        )

        adapter = _ConsentGateAdapter(consent_manager=mock_manager)
        result = await adapter.has_consent(user_id=42, tenant_id=1)

        assert result is False

    async def test_has_consent_fail_secure_on_exception(self) -> None:
        from src.core.copilot.council.factory import _ConsentGateAdapter

        mock_manager = AsyncMock()
        mock_manager.get_consent_categories.side_effect = RuntimeError("DB unavailable")

        adapter = _ConsentGateAdapter(consent_manager=mock_manager)
        result = await adapter.has_consent(user_id=42, tenant_id=1)

        assert result is False

    def test_consent_gate_protocol_is_async(self) -> None:
        from src.core.copilot.council.members.privacy_officer import ConsentGate

        assert inspect.iscoroutinefunction(ConsentGate.has_consent)


@pytest.mark.unit
class TestCoordinatorTwinProfileFromContext:
    def test_build_context_reads_from_context_snapshot(self) -> None:
        from src.core.copilot.council.coordinator import AgentCouncil

        source = inspect.getsource(AgentCouncil._build_context)
        assert "context_snapshot" in source

    def test_twin_profile_none_check_present(self) -> None:
        from src.core.copilot.council.coordinator import AgentCouncil

        source = inspect.getsource(AgentCouncil._build_context)
        assert "twin_profile" in source


@pytest.mark.unit
class TestPrivacyOfficerConsentActivation:
    def test_privacy_officer_awaits_consent_gate(self) -> None:
        from src.core.copilot.council.members.privacy_officer import PrivacyOfficer

        source = inspect.getsource(PrivacyOfficer._deliberate_inner)
        assert "await self._consent_gate.has_consent" in source

    def test_privacy_officer_skips_consent_check_without_twin_profile(self) -> None:
        from src.core.copilot.council.members.privacy_officer import PrivacyOfficer

        source = inspect.getsource(PrivacyOfficer._deliberate_inner)
        assert "twin_profile is not None" in source
