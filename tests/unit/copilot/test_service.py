"""
Unit tests for CopilotService.handle_turn.

Test taxonomy per CLAUDE.md kwaliteitsloop:
    - Happy paths      (approved, modified)
    - Unhappy paths    (blocked, council crash, LLM parse failure)
    - Security tests   (generic refusal leaks no internals, tenant isolation)
    - Behavioral test  (user sees correct verdict + message)

Markers:
    @pytest.mark.unit
    @pytest.mark.security
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import uuid
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)
from src.core.copilot.llm_handler import LLMHandler
from src.core.copilot.proposal_builder import ProposalBuilder
from src.core.copilot.schemas import CopilotAction
from src.core.copilot.service import CopilotService
from src.core.llm.llm_client import (
    LLMClient,
    LLMConfig,
    LLMMessage,
    LLMModel,
    LLMProvider,
    LLMResponse,
)


class MockLLMProvider(LLMClient):
    """Minimal provider for unit testing."""

    def __init__(self) -> None:
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model=LLMModel.GPT_4,
            api_key="fake",
        )
        super().__init__(config)

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        return LLMResponse(content="", model="", provider="")

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return LLMResponse(content="", model="", provider="")


def _make_council_decision(verdict: DecisionVerdict, **overrides: Any) -> CouncilDecision:
    """Factory for CouncilDecision test objects."""
    officer_verdicts = overrides.get(
        "officer_verdicts",
        (
            OfficerVerdict(
                officer_name="ComplianceOfficer",
                officer_version="1.0.0",
                verdict=VerdictType.APPROVE,
                reason_code="OK",
                reason_text="OK",
                evidence={},
                deliberation_ms=100,
                confidence=1.0,
            ),
        ),
    )
    return CouncilDecision(
        proposal_id=uuid4(),
        tenant_id=1,
        user_id=1,
        verdict=verdict,
        officer_verdicts=officer_verdicts,
        explanation_for_user="Test explanation",
        decision_hash="hash",
        previous_decision_hash=None,
        deliberation_ms=200,
        modifications=overrides.get("modifications"),
        hitl_request_id=overrides.get("hitl_request_id"),
    )


def _make_service(
    council: Any | None = None,
    llm_handler: Any | None = None,
    proposal_builder: Any | None = None,
    hitl_repo: Any | None = None,
    tool_broker: Any | None = None,
    audit_writer: Any | None = None,
) -> CopilotService:
    """Factory for CopilotService with optional mocked parts."""
    if council is None:
        council = MagicMock()
        council.deliberate = AsyncMock()
    if llm_handler is None:
        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock()
        llm_handler.model_id = "deepseek-chat-v3.1"
        llm_handler.model_version = "v3.1"
    if proposal_builder is None:
        proposal_builder = ProposalBuilder()
    return CopilotService(
        council=council,
        llm_handler=llm_handler,
        proposal_builder=proposal_builder,
        hitl_repo=hitl_repo,
        tool_broker=tool_broker,
        audit_writer=audit_writer,
    )


@pytest.mark.unit
class TestHandleTurnApproved:
    """APPROVED verdict path."""

    async def test_handle_turn_approved_returns_action(self) -> None:
        action = CopilotAction(
            message="Navigating home",
            action="navigate",
            action_params={"page": "home"},
            confidence=0.95,
            reasoning="User asked for home",
        )
        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock(return_value=action)
        llm_handler.model_id = "deepseek-chat-v3.1"
        llm_handler.model_version = "v3.1"

        decision = _make_council_decision(DecisionVerdict.APPROVED)
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        service = _make_service(council=council, llm_handler=llm_handler)
        response = await service.handle_turn(
            tenant_id=42,
            user_id=7,
            message="Go home",
            context={},
        )

        assert response.verdict == "approved"
        assert response.message == "Navigating home"
        assert response.action == "navigate"
        assert response.action_params == {"page": "home"}
        assert response.confidence == 0.95
        assert response.explanation_url is not None


@pytest.mark.unit
class TestHandleTurnModified:
    """MODIFIED verdict path."""

    async def test_handle_turn_modified_applies_mods(self) -> None:
        action = CopilotAction(
            message="Exporting data",
            action="export_data",
            action_params={"scope": "all"},
            confidence=0.8,
            reasoning="User asked for export",
        )
        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock(return_value=action)
        llm_handler.model_id = "m"
        llm_handler.model_version = "v1"

        modifications = {
            "EthicsOfficer": {
                "action_params": {"scope": "limited", "add_warning": True},
                "reasoning": "Limit scope for privacy",
            }
        }
        decision = _make_council_decision(
            DecisionVerdict.MODIFIED,
            modifications=modifications,
        )
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        service = _make_service(council=council, llm_handler=llm_handler)
        response = await service.handle_turn(
            tenant_id=1,
            user_id=1,
            message="Export data",
            context={},
        )

        assert response.verdict == "modified"
        assert response.action_params["scope"] == "limited"
        assert response.action_params["add_warning"] is True


@pytest.mark.unit
class TestHandleTurnHitl:
    """HITL_REQUIRED verdict path."""

    async def test_handle_turn_hitl_required_persists_request(self) -> None:
        # `local__send_email` en niet `send_email` (ADR-036 OP-78). De kale naam heeft geen
        # uitvoerder: hij staat alleen in `PII_ACTION_PREFIXES` als voorvoegsel om PII-acties te
        # herkennen, en `is_known_tool` weigert hem. Een ticket ervoor kon dus nooit worden
        # verzilverd -- de broker weigert de aanroep bij uitvoering. Deze test legde daarmee een
        # scenario vast dat in productie niet kan aflopen. De echte tool staat in
        # `local_registry.py:90`.
        action = CopilotAction(
            message="Bulk email",
            action="local__send_email",
            action_params={"recipients": ["a@b.com"]},
            confidence=0.7,
            reasoning="Bulk send",
        )
        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock(return_value=action)
        llm_handler.model_id = "m"
        llm_handler.model_version = "v1"

        decision = _make_council_decision(DecisionVerdict.HITL_REQUIRED)
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        hitl_repo = AsyncMock()
        hitl_repo.create_hitl_request = AsyncMock(return_value="hitl-uuid-123")

        service = _make_service(council=council, llm_handler=llm_handler, hitl_repo=hitl_repo)
        response = await service.handle_turn(
            tenant_id=1,
            user_id=1,
            message="Send bulk email",
            context={},
        )

        assert response.verdict == "hitl_required"
        assert response.hitl_request_id == "hitl-uuid-123"
        hitl_repo.create_hitl_request.assert_awaited_once()


@pytest.mark.unit
class TestHandleTurnDeferred:
    """DEFERRED verdict path."""

    async def test_handle_turn_deferred_returns_deferred_message(self) -> None:
        action = CopilotAction(
            message="Notify user",
            action="send_notification",
            action_params={},
            confidence=0.6,
            reasoning="Over budget",
        )
        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock(return_value=action)
        llm_handler.model_id = "m"
        llm_handler.model_version = "v1"

        decision = _make_council_decision(DecisionVerdict.DEFERRED)
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        service = _make_service(council=council, llm_handler=llm_handler)
        response = await service.handle_turn(
            tenant_id=1,
            user_id=1,
            message="Notify",
            context={},
        )

        assert response.verdict == "deferred"
        assert "deferred" in response.message.lower()


@pytest.mark.unit
@pytest.mark.security
class TestHandleTurnBlocked:
    """BLOCKED verdict and security boundaries."""

    async def test_handle_turn_blocked_returns_generic_refusal(self) -> None:
        action = CopilotAction(
            message="Delete everything",
            action="delete_all",
            action_params={},
            confidence=0.9,
            reasoning="User asked",
        )
        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock(return_value=action)
        llm_handler.model_id = "m"
        llm_handler.model_version = "v1"

        decision = _make_council_decision(DecisionVerdict.BLOCKED)
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        service = _make_service(council=council, llm_handler=llm_handler)
        response = await service.handle_turn(
            tenant_id=1,
            user_id=1,
            message="Delete everything",
            context={},
            language="en",
        )

        assert response.verdict == "blocked"
        assert "cannot be completed" in response.message
        # Internal reason must NOT leak
        assert "Test explanation" != response.message

    async def test_llm_invalid_json_retries_once(self) -> None:
        """LLMHandler retries internally; CopilotService sees approved."""
        provider = MockLLMProvider()
        bad_json = LLMResponse(content="not json", model="m", provider="p", success=True)
        good_json = LLMResponse(
            content='{"message":"OK","action":null,"action_params":{},"confidence":0.5,"reasoning":"OK"}',
            model="m",
            provider="p",
            success=True,
        )
        provider.complete_json = AsyncMock(  # type: ignore[method-assign]
            side_effect=[bad_json, good_json]
        )

        llm_handler = LLMHandler(provider)
        council = MagicMock()
        council.deliberate = AsyncMock(
            return_value=_make_council_decision(DecisionVerdict.APPROVED)
        )

        service = _make_service(council=council, llm_handler=llm_handler)
        response = await service.handle_turn(
            tenant_id=1,
            user_id=1,
            message="Hello",
            context={},
        )

        # Retry happens inside LLMHandler, so complete_json is called twice
        assert provider.complete_json.await_count == 2
        assert response.verdict == "approved"

    async def test_llm_invalid_json_after_retry_returns_blocked(self) -> None:
        """ValidationError after internal retry → BLOCKED response."""
        provider = MockLLMProvider()
        provider.complete_json = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResponse(content="bad json", model="m", provider="p", success=True)
        )

        llm_handler = LLMHandler(provider)
        council = MagicMock()

        service = _make_service(council=council, llm_handler=llm_handler)
        response = await service.handle_turn(
            tenant_id=1,
            user_id=1,
            message="Hello",
            context={},
        )

        # Internal retry inside LLMHandler (2 calls to provider)
        assert provider.complete_json.await_count == 2
        assert response.verdict == "blocked"
        council.deliberate.assert_not_called()

    async def test_council_exception_returns_blocked(self) -> None:
        action = CopilotAction(
            message="OK",
            action=None,
            action_params={},
            confidence=0.5,
            reasoning="OK",
        )
        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock(return_value=action)
        llm_handler.model_id = "m"
        llm_handler.model_version = "v1"

        council = MagicMock()
        council.deliberate = AsyncMock(side_effect=RuntimeError("Council crashed"))

        service = _make_service(council=council, llm_handler=llm_handler)
        response = await service.handle_turn(
            tenant_id=1,
            user_id=1,
            message="Hello",
            context={},
        )

        assert response.verdict == "blocked"

    async def test_tenant_id_not_taken_from_context_param(self) -> None:
        """tenant_id passed as parameter wins over any context value."""
        action = CopilotAction(
            message="Navigating",
            action="navigate",
            action_params={},
            confidence=0.9,
            reasoning="Test",
        )
        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock(return_value=action)
        llm_handler.model_id = "m"
        llm_handler.model_version = "v1"

        decision = _make_council_decision(DecisionVerdict.APPROVED)
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        service = _make_service(council=council, llm_handler=llm_handler)
        # Pass a malicious tenant_id inside context — must be ignored
        response = await service.handle_turn(
            tenant_id=42,
            user_id=7,
            message="Go",
            context={"tenant_id": 99, "user_id": 88},
        )

        assert response.verdict == "approved"
        # Verify the proposal was built with the real tenant_id, not from context
        call_args = council.deliberate.call_args[0][0]
        assert call_args.tenant_id == 42
        assert call_args.user_id == 7


@pytest.mark.unit
class TestCritical1CapabilityContext:
    """CRITICAL-1: handle_turn() must augment context with platform capabilities."""

    async def test_handle_turn_augments_context_with_capabilities(self) -> None:
        """Raw context dict must be augmented with capability snapshot."""
        action = CopilotAction(
            message="OK",
            action="test_action",
            action_params={},
            confidence=0.5,
            reasoning="Test",
        )
        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock(return_value=action)
        llm_handler.model_id = "m"
        llm_handler.model_version = "v1"

        decision = _make_council_decision(DecisionVerdict.APPROVED)
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        service = _make_service(council=council, llm_handler=llm_handler)
        await service.handle_turn(
            tenant_id=42,
            user_id=7,
            message="Hello",
            context={"user_pref": "dark_mode"},
        )

        # get_action must receive capability snapshot as separate parameter
        call_kwargs = llm_handler.get_action.call_args[1]
        assert "capabilities" in call_kwargs
        cap = call_kwargs["capabilities"]
        assert cap is not None
        assert cap["tenant_id"] == 42


@pytest.mark.unit
class TestHigh1AuditFailClosed:
    """HIGH-1: audit_writer fallback must not silently disable compliance."""

    async def test_noop_audit_raises_on_compliance_call(self) -> None:
        """Calling audit methods without a real audit_writer must raise."""
        from src.core.copilot.service import _FailClosedAudit

        audit = _FailClosedAudit()
        with pytest.raises(RuntimeError, match="audit_writer not configured"):
            await audit.log_user_response(
                signal_id=uuid4(), tenant_id=1, user_id=1, action_type="test", params={}
            )


@pytest.mark.unit
class TestHigh2BlockedResponseUuid:
    """HIGH-2: blocked responses must have a traceable decision_id."""

    async def test_blocked_response_has_valid_uuid(self) -> None:
        """On LLM failure, decision_id must be a valid UUID, not empty."""
        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock(side_effect=RuntimeError("LLM down"))
        llm_handler.model_id = "m"
        llm_handler.model_version = "v1"

        service = _make_service(llm_handler=llm_handler)
        response = await service.handle_turn(
            tenant_id=1,
            user_id=1,
            message="Hello",
            context={},
        )

        assert response.verdict == "blocked"
        assert response.decision_id != ""
        # Must be a valid UUID
        uuid_obj = uuid.UUID(response.decision_id)
        assert str(uuid_obj) == response.decision_id

    async def test_council_error_blocked_response_has_valid_uuid(self) -> None:
        """On Council failure, decision_id must be a valid UUID, not empty."""
        action = CopilotAction(
            message="OK", action=None, action_params={}, confidence=0.5, reasoning="OK"
        )
        llm_handler = MagicMock()
        llm_handler.get_action = AsyncMock(return_value=action)
        llm_handler.model_id = "m"
        llm_handler.model_version = "v1"

        council = MagicMock()
        council.deliberate = AsyncMock(side_effect=RuntimeError("Council crashed"))

        service = _make_service(council=council, llm_handler=llm_handler)
        response = await service.handle_turn(tenant_id=1, user_id=1, message="Hello", context={})

        assert response.verdict == "blocked"
        assert response.decision_id != ""
        uuid_obj = uuid.UUID(response.decision_id)
        assert str(uuid_obj) == response.decision_id


@pytest.mark.unit
class TestHigh3ActionValidation:
    """HIGH-3: _execute_decision must validate action exists before executing."""

    async def test_execute_unknown_tool_raises(self) -> None:
        """Executing an unregistered tool must raise so audit/guard can track the failure."""
        from src.core.tool_broker.exceptions import ToolExecutionException

        action = CopilotAction(
            message="Do it",
            action="unknown_tool",
            action_params={},
            confidence=0.9,
            reasoning="Test",
        )
        proposal = ProposalBuilder().build(
            tenant_id=1,
            user_id=1,
            action=action,
            trigger=ProposalTrigger.USER_REQUEST,
            model_id="m",
            model_version="v1",
            context_snapshot={},
        )
        decision = _make_council_decision(DecisionVerdict.APPROVED)

        tool_broker = MagicMock()
        tool_broker.execute_tool = AsyncMock(
            side_effect=ToolExecutionException(
                tool_name="unknown_tool", error_detail="Tool not found"
            )
        )

        audit_writer = AsyncMock()
        service = _make_service(tool_broker=tool_broker, audit_writer=audit_writer)
        with pytest.raises(ToolExecutionException):
            await service._execute_decision(proposal, decision)

        tool_broker.execute_tool.assert_awaited_once()

    async def test_execute_decision_passes_agent_id_to_tool_broker(self) -> None:
        """AUDIT-001: _execute_decision must pass agent_id="copilot" to execute_tool().

        Without agent_id, ToolPermissionManager.is_tool_allowed(agent_id or "", ...)
        treats the caller as an unregistered agent and denies every action -- crashing
        every Council-approved decision after it has already been written to the
        immutable audit hash-chain. "copilot" is the identity already registered in
        config/tool_permissions.yml and already used by _ToolBrokerAdapter for the
        analogous Council-deliberation-time check (factory.py:132).
        """
        action = CopilotAction(
            message="Send it",
            action="send_notification",
            action_params={},
            confidence=0.9,
            reasoning="Test",
        )
        proposal = ProposalBuilder().build(
            tenant_id=1,
            user_id=1,
            action=action,
            trigger=ProposalTrigger.USER_REQUEST,
            model_id="m",
            model_version="v1",
            context_snapshot={},
        )
        decision = _make_council_decision(DecisionVerdict.APPROVED)

        tool_broker = MagicMock()
        tool_broker.execute_tool = AsyncMock(return_value={"status": "ok"})

        audit_writer = AsyncMock()
        service = _make_service(tool_broker=tool_broker, audit_writer=audit_writer)
        await service._execute_decision(proposal, decision)

        tool_broker.execute_tool.assert_awaited_once()


def _make_proposal(action_type: str = "send_notification", **overrides: Any) -> Proposal:
    fields: dict[str, Any] = {
        "tenant_id": 1,
        "user_id": 1,
        "trigger": ProposalTrigger.PROACTIVE_MONITOR,
        "action_type": action_type,
        "action_params": {"title": "Signal"},
        "reasoning": "proactive monitor detected a signal",
        "data_classification": DataClassification.INTERNAL,
        "confidence": 1.0,
        "model_id": "proactive-monitor:test",
        "model_version": "1.0",
        "context_snapshot": {},
    }
    fields.update(overrides)
    return Proposal(**fields)


@pytest.mark.unit
class TestSubmitProactiveProposalHitl:
    """ADR-036 OP-167 (open-punten-opruiming dag 1): submit_proactive_proposal gooide een
    HITL_REQUIRED-verdict eerder ongebruikt weg -- het besluit bereikte nooit een mens.
    """

    async def test_hitl_required_creates_a_ticket(self) -> None:
        # `local__send_email`, geen `send_notification`: zelfde reden als
        # `TestHandleTurnHitl` hierboven -- `is_known_tool()` moet True geven, en
        # `send_notification` (de default-actie van de enige echte aanroeper,
        # `monitor.py::propose_to_council`) staat NERGENS in een tool-registry. Zie
        # `test_a_real_proactive_signal_never_raises_even_though_its_tool_is_unregistered`
        # hieronder voor precies dat scenario.
        decision = _make_council_decision(DecisionVerdict.HITL_REQUIRED)
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        hitl_repo = AsyncMock()
        hitl_repo.create_hitl_request = AsyncMock(return_value="hitl-uuid-proactive")

        service = _make_service(council=council, hitl_repo=hitl_repo)
        proposal = _make_proposal(action_type="local__send_email")

        result = await service.submit_proactive_proposal(proposal)

        assert result.verdict == DecisionVerdict.HITL_REQUIRED
        hitl_repo.create_hitl_request.assert_awaited_once()
        kwargs = hitl_repo.create_hitl_request.await_args.kwargs
        assert kwargs["tenant_id"] == proposal.tenant_id
        assert kwargs["user_id"] == proposal.user_id
        assert kwargs["decision_id"] == str(decision.decision_id)
        assert kwargs["action_type"] == "local__send_email"
        assert kwargs["action_params"] == {"title": "Signal"}

    async def test_hitl_required_without_a_configured_repo_does_not_crash(self) -> None:
        """Zonder hitl_repo (net als handle_turn's `if self._hitl_repo:`-guard) wordt er
        geen ticket geprobeerd -- geen crash, het verdict komt gewoon terug."""
        decision = _make_council_decision(DecisionVerdict.HITL_REQUIRED)
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        service = _make_service(council=council, hitl_repo=None)
        proposal = _make_proposal(action_type="local__send_email")

        result = await service.submit_proactive_proposal(proposal)

        assert result.verdict == DecisionVerdict.HITL_REQUIRED

    async def test_approved_verdict_never_creates_a_ticket(self) -> None:
        # Geen `tool_broker` meegegeven: `_execute_decision()` no-opt dan meteen
        # (`if not self._tool_broker: return None`), dus deze test hoeft geen
        # audit_writer/tool_broker-uitvoerpad op te tuigen -- hij toetst alleen dat een
        # APPROVED-verdict de HITL-ticketcode niet raakt.
        decision = _make_council_decision(DecisionVerdict.APPROVED)
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        hitl_repo = AsyncMock()
        service = _make_service(council=council, hitl_repo=hitl_repo)
        proposal = _make_proposal(action_type="local__send_email")

        await service.submit_proactive_proposal(proposal)

        hitl_repo.create_hitl_request.assert_not_awaited()

    async def test_a_real_proactive_signal_never_raises_even_though_its_tool_is_unregistered(
        self,
    ) -> None:
        """Regressiebewijs voor het exacte scenario van de ENIGE productie-aanroeper.

        `monitor.py::propose_to_council` heeft geen try/except om
        `submit_proactive_proposal()` heen. Zou deze functie hier een exception gooien
        (het `handle_turn`-patroon), dan crasht de achtergrondtaak van ELKE proactieve
        melding die ooit HITL_REQUIRED wordt -- strikt slechter dan de oude bug (een
        verdict dat stil werd weggegooid). In plaats daarvan: loggen en teruggeven,
        zonder ticket EN zonder exception.
        """
        decision = _make_council_decision(DecisionVerdict.HITL_REQUIRED)
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        hitl_repo = AsyncMock()
        service = _make_service(council=council, hitl_repo=hitl_repo)
        proposal = _make_proposal(action_type="send_notification")

        result = await service.submit_proactive_proposal(proposal)

        assert result.verdict == DecisionVerdict.HITL_REQUIRED
        hitl_repo.create_hitl_request.assert_not_awaited()

    async def test_an_unauthorized_identity_does_not_raise_either(self) -> None:
        """Gate 2-bevinding: `create_hitl_request` gebruikt hier de DEFAULT
        `executing_identity` ('copilot', geen agent-eigen identiteit) en `copilot` is niet
        voor elke tool geautoriseerd (`ToolPermissionManager`) -- dat geeft `PermissionError`,
        een ANDERE exception-klasse dan de onbekende-tool-weigering die de
        `_is_known_tool`-precheck al afvangt. Zelfde reden om hem te vangen: geen try/except
        bij de enige echte aanroeper."""
        decision = _make_council_decision(DecisionVerdict.HITL_REQUIRED)
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=decision)

        hitl_repo = AsyncMock()
        hitl_repo.create_hitl_request = AsyncMock(
            side_effect=PermissionError("copilot mag deze tool niet uitvoeren")
        )
        service = _make_service(council=council, hitl_repo=hitl_repo)
        proposal = _make_proposal(action_type="local__send_email")

        result = await service.submit_proactive_proposal(proposal)

        assert result.verdict == DecisionVerdict.HITL_REQUIRED
        hitl_repo.create_hitl_request.assert_awaited_once()


@pytest.mark.unit
class TestInputGuardOpDeChatdeur:
    """De inhoudswachter staat VOOR alles in `handle_turn` (2026-09-22).

    **Waarom dit een test op `handle_turn` is en niet op de wachter zelf.** De wachter heeft
    eigen tests (`tests/unit/governance/test_input_guard.py`) en een architectuurbewaker legt
    vast DAT hij wordt aangeroepen. Wat hier wordt gemeten is de derde vraag: doet de chatdeur
    er ook het juiste MEE -- weigeren, met de categorie, en zonder de LLM of de Council te
    hebben aangeraakt.

    Tot 2026-09-22 stond op dit pad geen enkele inhoudscontrole (gemeten: nul treffers op
    `detect_pii` in `copilot/service.py`).
    """

    #: Geldig volgens de elfproef -- een willekeurig getal van negen cijfers wordt door de
    #: detector NIET gevonden en zou deze test hol maken.
    BSN = "123456782"

    async def test_een_bsn_in_de_chat_wordt_geweigerd_voor_het_taalmodel(self) -> None:
        service = _make_service()

        response = await service.handle_turn(
            tenant_id=1,
            user_id=7,
            message=f"Plan een training voor BSN {self.BSN}",
            context={},
        )

        assert response.verdict == "blocked"
        assert "bsn" in response.message, (
            "De gebruiker moet de CATEGORIE horen, anders weet hij niet wat eruit moet -- en dan "
            "is de wachter een muur zonder deur (AI Act art. 14)."
        )
        assert self.BSN not in response.message, (
            "Het BSN staat in het antwoord aan de gebruiker. De wachter lekt dan precies wat hij "
            "tegenhield."
        )
        assert response.decision_id, "Zonder decision_id is er geen recht op uitleg."

        service._llm_handler.get_action.assert_not_awaited()  # type: ignore[attr-defined]
        service._council.deliberate.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_een_gewone_vraag_bereikt_het_taalmodel_wel(self) -> None:
        """De tegenrichting. Zonder deze test is "weiger alles" een geldige oplossing."""
        service = _make_service()
        service._llm_handler.get_action = AsyncMock(  # type: ignore[attr-defined]
            side_effect=RuntimeError("tot hier is genoeg -- het model is bereikt")
        )

        response = await service.handle_turn(
            tenant_id=1,
            user_id=7,
            message="Vat de vaardighedenkloof samen voor het team Finance",
            context={},
        )

        # De LLM-fout wordt netjes een blocked response; wat deze test meet is dat de wachter
        # hem niet EERDER heeft tegengehouden.
        service._llm_handler.get_action.assert_awaited_once()  # type: ignore[attr-defined]
        assert response.verdict == "blocked"
        assert "bsn" not in response.message

    async def test_een_bsn_in_de_CONTEXT_wordt_ook_geweigerd(self) -> None:
        """Hetzelfde verzoek, een JSON-veld verderop -- dat was het gat uit Gate 2.

        `context` komt rechtstreeks van de client, is `dict[str, Any]` en heeft -- anders dan
        `message`, die op 2000 tekens staat -- GEEN `max_length` in `CopilotTurnRequest`
        (gemeten 2026-09-22). Het gaat via `_augment_context` naar het taalmodel EN naar
        `proposal.context_snapshot`, dus naar de Council en daarmee de auditketen. De eerste
        versie van de wachter las alleen `message`.
        """
        service = _make_service()

        response = await service.handle_turn(
            tenant_id=1,
            user_id=7,
            message="vat de kloof samen",
            context={"notitie": f"BSN {self.BSN}"},
        )

        assert response.verdict == "blocked"
        assert self.BSN not in response.message
        service._llm_handler.get_action.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_de_weigering_is_engels_voor_een_engelse_gebruiker(self) -> None:
        """Anders weet hij niet wat eruit moet, en dan is de wachter een muur zonder deur."""
        service = _make_service()

        response = await service.handle_turn(
            tenant_id=1,
            user_id=7,
            message=f"Schedule training for BSN {self.BSN}",
            context={},
            language="en",
        )

        assert response.verdict == "blocked"
        assert "refused" in response.message
        assert "geweigerd" not in response.message


def _llm_returning(action_name: str) -> MagicMock:
    llm_handler = MagicMock()
    llm_handler.get_action = AsyncMock(
        return_value=CopilotAction(
            message="Ik stuur de aanmaning",
            action=action_name,
            action_params={"channel": "email"},
            confidence=0.9,
            reasoning="Gebruiker vroeg om een aanmaning",
        )
    )
    llm_handler.model_id = "m"
    llm_handler.model_version = "v1"
    return llm_handler


def _approving_council() -> MagicMock:
    council = MagicMock()
    council.deliberate = AsyncMock(return_value=_make_council_decision(DecisionVerdict.APPROVED))
    return council


def _working_broker() -> MagicMock:
    tool_broker = MagicMock()
    tool_broker.execute_tool = AsyncMock(return_value={"status": "ok"})
    return tool_broker


@pytest.mark.unit
@pytest.mark.security
class TestActionWithoutExecutorIsBlockedBeforeCouncil:
    """Een actie zonder uitvoerder wordt geweigerd VOOR Council en uitvoering, nooit een 500.

    Gemeten in de draaiende app (2026-10-04): het taalmodel koos `action_type='confirm'`, de
    Council keurde goed, en `ToolBrokerService.execute_tool` gooide TB_2002 "Unknown tool
    category" -- een HTTP 500 NA een goedkeuring. `confirm` staat in het copilot-profiel van
    `config/tool_permissions.yml` (namespace council_action) maar heeft geen uitvoerder.
    """

    @pytest.mark.parametrize("action_name", ["made_up_tool"])
    async def test_the_turn_is_blocked(self, action_name: str) -> None:
        service = _make_service(
            council=_approving_council(),
            llm_handler=_llm_returning(action_name),
            tool_broker=_working_broker(),
            audit_writer=AsyncMock(),
        )

        response = await service.handle_turn(
            tenant_id=1, user_id=1, message="stuur een aanmaning per e-mail", context={}
        )

        assert (response.verdict, response.action, response.action_params) == (
            "blocked",
            None,
            {},
        )

    async def test_the_council_is_never_asked(self) -> None:
        council = _approving_council()
        service = _make_service(
            council=council,
            llm_handler=_llm_returning("made_up_tool"),
            tool_broker=_working_broker(),
            audit_writer=AsyncMock(),
        )

        await service.handle_turn(
            tenant_id=1, user_id=1, message="stuur een aanmaning per e-mail", context={}
        )

        council.deliberate.assert_not_awaited()

    async def test_the_broker_is_never_called(self) -> None:
        tool_broker = _working_broker()
        service = _make_service(
            council=_approving_council(),
            llm_handler=_llm_returning("made_up_tool"),
            tool_broker=tool_broker,
            audit_writer=AsyncMock(),
        )

        await service.handle_turn(
            tenant_id=1, user_id=1, message="stuur een aanmaning per e-mail", context={}
        )

        tool_broker.execute_tool.assert_not_awaited()

    async def test_a_known_tool_still_reaches_the_broker(self) -> None:
        """Andere kant op: 'weiger alles' is geen geldige oplossing."""
        tool_broker = _working_broker()
        service = _make_service(
            council=_approving_council(),
            llm_handler=_llm_returning("create_task"),
            tool_broker=tool_broker,
            audit_writer=AsyncMock(),
        )

        await service.handle_turn(tenant_id=1, user_id=1, message="maak een taak", context={})

        tool_broker.execute_tool.assert_awaited_once()


def _llm_returning_no_action() -> MagicMock:
    llm_handler = _llm_returning("x")
    llm_handler.get_action = AsyncMock(
        return_value=CopilotAction(
            message="Hoe kan ik helpen?",
            action=None,
            action_params={},
            confidence=0.9,
            reasoning="Gewone gespreksbeurt",
        )
    )
    return llm_handler


@pytest.mark.unit
class TestConversationalTurnIsNotRefused:
    """Regressie op 23cdc8e8 (brief 2026-10-05, A-01): een beurt zonder echte actie
    (`noop` uit `proposal_builder`, of de gespreksacties clarify/confirm/unknown) is een
    gespreksantwoord. De voorcontrole 'actie zonder uitvoerder' mag die niet weigeren, en de
    broker mag er niet mee worden aangeroepen (anders TB_2002 -> 500)."""

    @pytest.mark.parametrize("action_name", [None, "clarify", "confirm", "unknown"])
    async def test_the_turn_is_answered_not_blocked(self, action_name: str | None) -> None:
        council = _approving_council()
        tool_broker = _working_broker()
        service = _make_service(
            council=council,
            llm_handler=(
                _llm_returning_no_action() if action_name is None else _llm_returning(action_name)
            ),
            tool_broker=tool_broker,
            audit_writer=AsyncMock(),
        )

        response = await service.handle_turn(tenant_id=1, user_id=1, message="hallo", context={})

        assert response.verdict != "blocked"
        council.deliberate.assert_awaited_once()
        tool_broker.execute_tool.assert_not_awaited()
