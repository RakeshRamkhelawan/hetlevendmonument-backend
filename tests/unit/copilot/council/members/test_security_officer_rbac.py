"""RC-004: RBACService.user_has_scope_for() must exist and be wired in SecurityOfficer.

Red phase: tests 1+2 FAIL before the fix (AttributeError: RBACService has no user_has_scope_for).
Test 3 uses a mock so it verifies wiring only -- also fails before fix due to spec= restriction.
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, create_autospec

from src.core.auth.rbac import RBACService
from src.core.copilot.council.types import DeliberationContext


def _make_context() -> DeliberationContext:
    return DeliberationContext(
        tenant_settings={},
        user_preferences={},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=500,
        request_id=uuid.uuid4(),
    )


class TestRBACServiceHasScopeFor:
    """user_has_scope_for() must exist on RBACService and evaluate action_type correctly."""

    @pytest.mark.asyncio
    async def test_method_exists_and_returns_bool(self) -> None:
        """user_has_scope_for() exists and returns a bool for a known action_type."""
        svc = RBACService()
        result = await svc.user_has_scope_for(user_id=1, action_type="send_notification")
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_unknown_action_type_denies(self) -> None:
        """Unknown action_type must be denied (fail-safe)."""
        svc = RBACService()
        result = await svc.user_has_scope_for(user_id=1, action_type="unknown:nonexistent_xyz")
        assert result is False

    @pytest.mark.asyncio
    async def test_security_officer_calls_user_has_scope_for_on_rbac(self) -> None:
        """SecurityOfficer._legacy_deliberate() calls user_has_scope_for -- no AttributeError."""
        from src.core.copilot.council.members.security_officer import SecurityOfficer
        from src.core.copilot.council.types import (
            Proposal,
            ProposalTrigger,
            DataClassification,
            VerdictType,
        )

        # `create_autospec` en niet `AsyncMock(spec=...)`: gemeten 2026-08-15 controleert
        # `spec=` de SIGNATUUR niet, dus een aanroep met een argument dat de echte functie
        # niet heeft blijft groen -- terwijl productie dan een TypeError geeft die de
        # SecurityOfficer als OFFICER_ERROR afvangt (SP-COUNCIL-GATE-001, Gate 2-review).
        mock_rbac = create_autospec(RBACService, instance=True)
        mock_rbac.user_has_scope_for.return_value = False

        mock_tool_broker = AsyncMock()
        mock_tool_broker.is_allowed.return_value = True

        mock_prompt_guard = MagicMock()
        mock_prompt_guard.scan.return_value = {"injection_detected": False, "patterns": []}

        officer = SecurityOfficer(
            tool_broker=mock_tool_broker,
            prompt_guard=mock_prompt_guard,
            rbac_checker=mock_rbac,
        )

        proposal = Proposal(
            tenant_id=1,
            user_id=42,
            trigger=ProposalTrigger.USER_REQUEST,
            action_type="send_notification",
            action_params={},
            reasoning="test",
            data_classification=DataClassification.PUBLIC,
            confidence=0.9,
            model_id="test-model",
            model_version="1.0",
            context_snapshot={},
        )

        verdict = await officer._legacy_deliberate(proposal, context=_make_context())

        # De tenant komt uit het VOORSTEL, niet uit een ambient ContextVar. Exact deze
        # vorm en niet `assert_called_once()`: dan zou de nieuwe parameter niet meer
        # bewezen worden en is de assertie een dekmantel in plaats van een bewijs.
        mock_rbac.user_has_scope_for.assert_called_once_with(42, "send_notification", tenant_id=1)
        assert verdict.verdict == VerdictType.VETO
        assert verdict.reason_code == "MISSING_SCOPE"

    @pytest.mark.asyncio
    async def test_the_cached_path_forwards_the_tenant_too(self) -> None:
        """De officier heeft TWEE identieke RBAC-aanroepen; beide moeten de tenant meegeven.

        `_legacy_deliberate` is vandaag de productieweg (`build_council()` geeft geen cache
        mee), `_actual_deliberate` is het cache-pad. Uit de Gate 2-review: een halve wijziging
        is anders niet zichtbaar, en dan valt `tenant_id` daar terug op `None` -> fail-closed
        -> elke broker-tool geweigerd, terwijl alle andere tests groen staan.
        """
        from src.core.copilot.council.members.security_officer import SecurityOfficer
        from src.core.copilot.council.types import (
            DataClassification,
            Proposal,
            ProposalTrigger,
            VerdictType,
        )

        mock_rbac = create_autospec(RBACService, instance=True)
        mock_rbac.user_has_scope_for.return_value = False

        mock_tool_broker = AsyncMock()
        mock_tool_broker.is_allowed.return_value = True

        mock_prompt_guard = MagicMock()
        mock_prompt_guard.scan.return_value = {"injection_detected": False, "patterns": []}

        officer = SecurityOfficer(
            tool_broker=mock_tool_broker,
            prompt_guard=mock_prompt_guard,
            rbac_checker=mock_rbac,
        )

        proposal = Proposal(
            tenant_id=7,
            user_id=42,
            trigger=ProposalTrigger.USER_REQUEST,
            action_type="send_notification",
            action_params={},
            reasoning="test",
            data_classification=DataClassification.PUBLIC,
            confidence=0.9,
            model_id="test-model",
            model_version="1.0",
            context_snapshot={},
        )

        verdict = await officer._actual_deliberate(proposal, context=_make_context())

        mock_rbac.user_has_scope_for.assert_called_once_with(42, "send_notification", tenant_id=7)
        assert verdict.verdict == VerdictType.VETO
        assert verdict.reason_code == "MISSING_SCOPE"
