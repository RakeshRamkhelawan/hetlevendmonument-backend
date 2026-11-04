"""
SP-C01-B: Twin consent opt-in + _augment_context tool catalog

B-009: UserTwinConsent defaults = True (opt-out, GDPR Art. 7 violation)
B-001: _augment_context() is a TODO stub -- LLM ziet geen tool catalog
"""

import inspect
import os

import pytest

os.environ.setdefault("TESTING", "1")


# ---------------------------------------------------------------------------
# B-009 -- UserTwinConsent GDPR opt-in defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTwinConsentDefaults:
    """SQLAlchemy mapped_column(default=X) is an INSERT-time default, not a Python
    attribute default. Tests use __table__ column inspection to verify the correct
    INSERT default is configured for each consent field."""

    def _get_insert_default(self, field: str) -> object:
        from src.core.learning.twin_models import UserTwinConsent

        col = UserTwinConsent.__table__.columns[field]
        if col.default is None:
            return None
        return col.default.arg

    def test_cross_session_memory_insert_default_is_false(self) -> None:
        """cross_session_memory INSERT default = False (GDPR Art. 7 opt-in)."""
        assert self._get_insert_default("cross_session_memory") is False, (
            "UserTwinConsent.cross_session_memory INSERT default is True -- GDPR opt-out (B-009)"
        )

    def test_behavior_tracking_insert_default_is_false(self) -> None:
        """behavior_tracking INSERT default = False (GDPR Art. 7 opt-in)."""
        assert self._get_insert_default("behavior_tracking") is False, (
            "UserTwinConsent.behavior_tracking INSERT default is True -- GDPR opt-out"
        )

    def test_profile_aggregation_insert_default_is_false(self) -> None:
        """profile_aggregation INSERT default = False (GDPR Art. 7 opt-in)."""
        assert self._get_insert_default("profile_aggregation") is False, (
            "UserTwinConsent.profile_aggregation INSERT default is True -- GDPR opt-out"
        )

    def test_ai_interventions_insert_default_is_false(self) -> None:
        """ai_interventions INSERT default = False (GDPR Art. 7 opt-in)."""
        assert self._get_insert_default("ai_interventions") is False, (
            "UserTwinConsent.ai_interventions INSERT default is True -- GDPR opt-out"
        )

    def test_consent_given_insert_default_is_false(self) -> None:
        """consent_given INSERT default = False (GDPR Art. 7 opt-in)."""
        assert self._get_insert_default("consent_given") is False, (
            "UserTwinConsent.consent_given INSERT default is True -- GDPR opt-out"
        )

    def test_status_insert_default_is_disabled(self) -> None:
        """status INSERT default = 'disabled' (GDPR opt-in -- new users start disabled)."""
        assert self._get_insert_default("status") == "disabled", (
            "UserTwinConsent.status INSERT default is 'enabled' -- GDPR opt-out"
        )

    def test_consent_can_be_explicitly_enabled(self) -> None:
        """UserTwinConsent kan worden ingeschakeld door expliciete keuze."""
        from src.core.learning.twin_models import UserTwinConsent

        consent = UserTwinConsent(
            cross_session_memory=True,
            behavior_tracking=True,
            profile_aggregation=True,
            ai_interventions=True,
            consent_given=True,
        )
        assert consent.cross_session_memory is True
        assert consent.behavior_tracking is True

    def test_consent_categories_all_defaults_are_false(self) -> None:
        """ConsentCategories alle defaults = False (GDPR Art. 7 opt-in)."""
        from src.core.learning.consent.consent_manager import ConsentCategories

        cats = ConsentCategories()
        assert cats.cross_session_memory is False, (
            "ConsentCategories.cross_session_memory default is True -- GDPR opt-out"
        )
        assert cats.behavior_tracking is False, (
            "ConsentCategories.behavior_tracking default is True -- GDPR opt-out"
        )
        assert cats.profile_aggregation is False, (
            "ConsentCategories.profile_aggregation default is True -- GDPR opt-out"
        )
        assert cats.ai_interventions is False, (
            "ConsentCategories.ai_interventions default is True -- GDPR opt-out"
        )

    def test_get_or_create_consent_no_hardcoded_true(self) -> None:
        """_get_or_create_consent gebruikt geen hardcoded True voor consent velden."""
        from src.core.learning.consent.consent_manager import TwinConsentManager

        source = inspect.getsource(TwinConsentManager._get_or_create_consent)
        for field in (
            "consent_given",
            "behavior_tracking",
            "profile_aggregation",
            "ai_interventions",
            "cross_session_memory",
        ):
            assert f"{field}=True" not in source, (
                f"_get_or_create_consent heeft nog hardcoded {field}=True (B-009)"
            )


# ---------------------------------------------------------------------------
# B-001 -- _augment_context tool catalog
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAugmentContext:
    def test_augment_context_no_longer_stub(self) -> None:
        """_augment_context mag geen TODO-stub meer zijn (B-001)."""
        from src.core.copilot.service import CopilotService

        source = inspect.getsource(CopilotService._augment_context)
        # Exclude type-annotation TODO(TYPE) markers -- those are sprint markers, not feature stubs
        non_type_todos = [ln for ln in source.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
        assert not non_type_todos, (
            "_augment_context is nog een TODO-stub (B-001) -- "
            "LLM hallucineert acties die niet bestaan. "
            f"Gevonden: {non_type_todos[:2]}"
        )

    def test_augment_context_injects_agents_key(self) -> None:
        """_augment_context injecteert 'agents' in de capabilities."""
        from src.core.copilot.service import CopilotService

        source = inspect.getsource(CopilotService._augment_context)
        assert "agents" in source, "_augment_context injecteert geen 'agents' catalog"

    def test_augment_context_injects_tools_key(self) -> None:
        """_augment_context injecteert 'tools' in de capabilities."""
        from src.core.copilot.service import CopilotService

        source = inspect.getsource(CopilotService._augment_context)
        assert "tools" in source, "_augment_context injecteert geen 'tools' catalog"

    @pytest.mark.asyncio
    async def test_augment_context_behavioral_capabilities_not_empty(self) -> None:
        """Behavioral: _augment_context vult _platform_capabilities met agents + tools."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.core.copilot.service import CopilotService

        service = CopilotService(
            council=MagicMock(),
            llm_handler=MagicMock(),
            proposal_builder=MagicMock(),
            audit_writer=AsyncMock(),
        )

        with (
            patch.object(service, "_get_available_agents", return_value=[{"name": "agent_1"}]),
            patch.object(service, "_get_allowed_tools", return_value=[{"name": "tool_1"}]),
        ):
            result = await service._augment_context(tenant_id=1, context={})

        caps = result.get("_platform_capabilities", {})
        assert caps.get("agents") == [{"name": "agent_1"}], (
            "_platform_capabilities.agents leeg of ontbrekend"
        )
        assert caps.get("tools") == [{"name": "tool_1"}], (
            "_platform_capabilities.tools leeg of ontbrekend"
        )

    @pytest.mark.asyncio
    async def test_augment_context_graceful_on_registry_error(self) -> None:
        """_augment_context returnt lege catalog bij registry-fout -- geen crash."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.core.copilot.service import CopilotService

        service = CopilotService(
            council=MagicMock(),
            llm_handler=MagicMock(),
            proposal_builder=MagicMock(),
            audit_writer=AsyncMock(),
        )

        with (
            patch.object(
                service, "_get_available_agents", side_effect=RuntimeError("registry down")
            ),
            patch.object(service, "_get_allowed_tools", return_value=[]),
        ):
            result = await service._augment_context(tenant_id=1, context={})

        caps = result.get("_platform_capabilities", {})
        assert "agents" in caps, "_platform_capabilities.agents ontbreekt bij fout"
        assert caps["agents"] == [], "agents moet leeg zijn bij fout"
