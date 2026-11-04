"""
Tests for src.core.copilot.council.governance_gate.

Covers:
- Happy path: Council approves -> decision returned
- Unhappy paths: BLOCKED, MODIFIED, HITL_REQUIRED, DEFERRED -> HTTPException(403)
- Council crash -> HTTPException(500)
- Tenant isolation: correct tenant_id/user_id passed to Council
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException

from src.core.copilot.council.governance_gate import require_council_approval
from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    OfficerVerdict,
    VerdictType,
)


class _FakeCouncil:
    """Fake Council that returns a configurable verdict."""

    def __init__(self, verdict: DecisionVerdict = DecisionVerdict.APPROVED) -> None:
        self.verdict = verdict
        self.last_proposal: Any | None = None

    async def deliberate(self, proposal: Any) -> CouncilDecision:
        self.last_proposal = proposal
        return CouncilDecision(
            proposal_id=UUID(int=1),
            tenant_id=proposal.tenant_id,
            user_id=proposal.user_id,
            verdict=self.verdict,
            officer_verdicts=(
                OfficerVerdict(
                    officer_name="ComplianceOfficer",
                    officer_version="1.0.0",
                    verdict=VerdictType.APPROVE,
                    reason_code="TEST_OK",
                    reason_text="test",
                    evidence={},
                    deliberation_ms=10,
                    confidence=1.0,
                ),
            ),
            explanation_for_user="test explanation",
            decision_hash="abc123",
            previous_decision_hash=None,
            deliberation_ms=100,
        )


class _CrashCouncil:
    """Council that always crashes."""

    async def deliberate(self, proposal: Any) -> CouncilDecision:
        raise RuntimeError("Council crash")


@pytest.mark.unit
async def test_require_council_approval_returns_decision_on_approve() -> None:
    council = _FakeCouncil(verdict=DecisionVerdict.APPROVED)

    decision = await require_council_approval(
        council=council,
        tenant_id=42,
        user_id=7,
        action_type="test.action",
        action_params={"key": "value"},
        reasoning="test reasoning",
    )

    assert decision.verdict == DecisionVerdict.APPROVED
    assert council.last_proposal is not None
    assert council.last_proposal.tenant_id == 42
    assert council.last_proposal.user_id == 7
    assert council.last_proposal.action_type == "test.action"


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_verdict",
    [
        DecisionVerdict.BLOCKED,
        DecisionVerdict.MODIFIED,
        DecisionVerdict.HITL_REQUIRED,
        DecisionVerdict.DEFERRED,
    ],
)
async def test_require_council_approval_raises_403_on_non_approve(
    bad_verdict: DecisionVerdict,
) -> None:
    council = _FakeCouncil(verdict=bad_verdict)

    with pytest.raises(HTTPException) as exc_info:
        await require_council_approval(
            council=council,
            tenant_id=1,
            user_id=1,
            action_type="test.action",
            action_params={},
            reasoning="test",
        )

    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    assert detail["code"] == "GOVERNANCE_BLOCKED"
    assert "decision_id" in detail
    assert detail["verdict"] == bad_verdict.value


@pytest.mark.unit
async def test_require_council_approval_raises_500_on_council_crash() -> None:
    council = _CrashCouncil()

    with pytest.raises(HTTPException) as exc_info:
        await require_council_approval(
            council=council,
            tenant_id=1,
            user_id=1,
            action_type="test.action",
            action_params={},
            reasoning="test",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["code"] == "COUNCIL_UNAVAILABLE"


@pytest.mark.unit
async def test_require_council_approval_passes_full_context() -> None:
    council = _FakeCouncil(verdict=DecisionVerdict.APPROVED)

    await require_council_approval(
        council=council,
        tenant_id=99,
        user_id=42,
        action_type="my_domain.my_action",
        action_params={"k": "v"},
        reasoning="because",
        data_classification=DataClassification.CONFIDENTIAL,
        confidence=0.95,
        model_id="gpt-4",
        model_version="2024-01",
        context_snapshot={"page": "dashboard"},
    )

    p = council.last_proposal
    assert p.data_classification == DataClassification.CONFIDENTIAL
    assert p.confidence == 0.95
    assert p.model_id == "gpt-4"
    assert p.model_version == "2024-01"
    assert p.context_snapshot == {"page": "dashboard"}


@pytest.mark.unit
class TestHitlTicketOnGovernanceBlock:
    """ADR-036 OP-167 (sprint dag 2): een HITL_REQUIRED-verdict op DEZE poort behandelde
    het verdict eerder identiek aan BLOCKED -- geen ticket, geen mens werd ooit gevraagd
    (AI Act art. 14). `require_council_approval` blijft altijd een 403 gooien (dat contract
    verandert niet -- deze poort laat uitsluitend APPROVED door), maar de 403-body draagt
    nu `hitl_request_id` zodra een ticket kon worden aangemaakt.
    """

    async def test_creates_a_ticket_and_puts_the_ref_in_the_403_body(self) -> None:
        council = _FakeCouncil(verdict=DecisionVerdict.HITL_REQUIRED)
        fake_db = AsyncMock()
        fake_repo = AsyncMock()
        fake_repo.create_hitl_request = AsyncMock(return_value="TICKET-REF-GG")

        with patch(
            "src.core.tool_broker.hitl_repository.HITLTicketRepository",
            return_value=fake_repo,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_council_approval(
                    council=council,
                    tenant_id=5,
                    user_id=9,
                    action_type="agentic.generate_workflow",
                    action_params={"prompt_length": 10},
                    reasoning="test",
                    db=fake_db,
                )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["hitl_request_id"] == "TICKET-REF-GG"
        fake_repo.create_hitl_request.assert_awaited_once()
        kwargs = fake_repo.create_hitl_request.await_args.kwargs
        assert kwargs["tenant_id"] == 5
        assert kwargs["user_id"] == 9
        assert kwargs["action_type"] == "agentic.generate_workflow"

    async def test_without_a_db_session_no_ticket_is_attempted(self) -> None:
        """Graceful degradation: een caller die (nog) geen db meegeeft krijgt gewoon de
        oude 403 terug, zonder crash en zonder ticket -- dit is het migratiepad totdat
        ELKE caller is bijgewerkt."""
        council = _FakeCouncil(verdict=DecisionVerdict.HITL_REQUIRED)

        with pytest.raises(HTTPException) as exc_info:
            await require_council_approval(
                council=council,
                tenant_id=5,
                user_id=9,
                action_type="agentic.generate_workflow",
                action_params={},
                reasoning="test",
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["hitl_request_id"] is None

    async def test_a_non_hitl_verdict_never_attempts_a_ticket_even_with_db(self) -> None:
        council = _FakeCouncil(verdict=DecisionVerdict.BLOCKED)
        fake_db = AsyncMock()

        with patch("src.core.tool_broker.hitl_repository.HITLTicketRepository") as repo_cls:
            with pytest.raises(HTTPException) as exc_info:
                await require_council_approval(
                    council=council,
                    tenant_id=5,
                    user_id=9,
                    action_type="agentic.generate_workflow",
                    action_params={},
                    reasoning="test",
                    db=fake_db,
                )

        assert exc_info.value.detail["hitl_request_id"] is None
        repo_cls.assert_not_called()

    async def test_ticket_refusal_does_not_raise_unexpectedly(self) -> None:
        """Gate 2-les uit dag 1: create_hitl_request kan zelf ValueError (onbekende tool,
        OP-90) of PermissionError (executing_identity niet geautoriseerd, OP-163) gooien.
        Beide moeten hier gevangen worden -- de 403 blijft normaal doorgaan, alleen zonder
        ticketverwijzing."""
        council = _FakeCouncil(verdict=DecisionVerdict.HITL_REQUIRED)
        fake_db = AsyncMock()
        fake_repo = AsyncMock()
        fake_repo.create_hitl_request = AsyncMock(
            side_effect=ValueError("Geen uitvoerder voor tool 'onbekend'")
        )

        with patch(
            "src.core.tool_broker.hitl_repository.HITLTicketRepository",
            return_value=fake_repo,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_council_approval(
                    council=council,
                    tenant_id=5,
                    user_id=9,
                    action_type="onbekend",
                    action_params={},
                    reasoning="test",
                    db=fake_db,
                )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["hitl_request_id"] is None

    async def test_ticket_action_params_used_instead_of_action_params_when_given(self) -> None:
        council = _FakeCouncil(verdict=DecisionVerdict.HITL_REQUIRED)
        fake_db = AsyncMock()
        fake_repo = AsyncMock()
        fake_repo.create_hitl_request = AsyncMock(return_value="TICKET-REF")

        with patch(
            "src.core.tool_broker.hitl_repository.HITLTicketRepository",
            return_value=fake_repo,
        ):
            with pytest.raises(HTTPException):
                await require_council_approval(
                    council=council,
                    tenant_id=5,
                    user_id=9,
                    action_type="test.action",
                    action_params={"arg_keys": ["employee_id"]},
                    ticket_action_params={"employee_id": "e-0"},
                    reasoning="test",
                    db=fake_db,
                )

        kwargs = fake_repo.create_hitl_request.await_args.kwargs
        assert kwargs["action_params"] == {"employee_id": "e-0"}
