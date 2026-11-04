import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.core.copilot.council.types import CouncilDecision, DecisionVerdict
from src.core.copilot.service import CopilotService
from src.core.copilot.schemas import CopilotAction
from src.core.copilot.council import Proposal


@pytest.mark.asyncio
class TestCG004_HitlRepoCopilotWiring:

    def _build_service(self, hitl_repo=None):
        return CopilotService(
            council=AsyncMock(),
            llm_handler=AsyncMock(),
            proposal_builder=MagicMock(),
            hitl_repo=hitl_repo,
            tool_broker=AsyncMock(),
            audit_writer=AsyncMock(),
            execution_guard=AsyncMock(),
            redis=AsyncMock(),
        )

    def _make_decision(self, verdict=DecisionVerdict.HITL_REQUIRED):
        return CouncilDecision(
            proposal_id=uuid4(),
            tenant_id=1,
            user_id=1,
            verdict=verdict,
            officer_verdicts=(),
            explanation_for_user="Reason",
            decision_hash="HASH",
            previous_decision_hash=None,
            deliberation_ms=10,
        )

    def _make_action(self):
        return CopilotAction(
            action="local__test",
            action_params={"param": "value"},
            message="Test message",
            confidence=0.9,
            reasoning="Because it's a test"
        )

    def _make_proposal(self, tenant_id=1, user_id=1):
        from src.core.copilot.council.types import DataClassification, ProposalTrigger
        return Proposal(
            proposal_id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            action_type="local__test",
            action_params={"param": "value"},
            trigger=ProposalTrigger.USER_REQUEST,
            model_id="gpt-4",
            model_version="1.0",
            reasoning="Test reasoning",
            data_classification=DataClassification.INTERNAL,
            confidence=0.9,
            context_snapshot={}
        )

    async def test_hitl_required_zonder_repo_retourneert_blocked(self):
        """ROOD voor fix: HITL_REQUIRED valt door naar _blocked_response als hitl_repo=None."""
        # Arrange: CopilotService ZONDER hitl_repo
        svc = self._build_service(hitl_repo=None)
        decision = self._make_decision(verdict=DecisionVerdict.HITL_REQUIRED)

        # Act
        response = await svc._route_verdict(decision, self._make_action(), self._make_proposal(), "nl")

        # Assert: blocked in plaats van hitl_required
        assert response.verdict == "blocked"
        assert response.hitl_request_id is None

    async def test_hitl_required_met_repo_retourneert_hitl_request_id(self):
        """GROEN na fix: HITL_REQUIRED retourneert verdict=hitl_required + hitl_request_id."""
        # Arrange
        mock_repo = AsyncMock()
        mock_repo.create_hitl_request = AsyncMock(return_value="hitl_abc123")
        svc = self._build_service(hitl_repo=mock_repo)
        decision = self._make_decision(verdict=DecisionVerdict.HITL_REQUIRED)

        # Act
        response = await svc._route_verdict(decision, self._make_action(), self._make_proposal(), "nl")

        # Assert
        assert response.verdict == "hitl_required"
        assert response.hitl_request_id == "hitl_abc123"
        mock_repo.create_hitl_request.assert_awaited_once()

    async def test_create_hitl_request_aangeroepen_met_correcte_tenant(self):
        """GROEN na fix: tenant_id in create_hitl_request komt van proposal, nooit van payload."""
        mock_repo = AsyncMock()
        mock_repo.create_hitl_request = AsyncMock(return_value="hitl_xyz")
        svc = self._build_service(hitl_repo=mock_repo)
        proposal = self._make_proposal(tenant_id=42, user_id=99)
        decision = self._make_decision(verdict=DecisionVerdict.HITL_REQUIRED)

        await svc._route_verdict(decision, self._make_action(), proposal, "nl")

        call_kwargs = mock_repo.create_hitl_request.call_args.kwargs
        assert call_kwargs["tenant_id"] == 42
        assert call_kwargs["user_id"] == 99

    async def test_approved_verdict_nooit_hitl_repo_aanroepen(self):
        """Regressie: APPROVED verdict raakt hitl_repo nooit aan."""
        mock_repo = AsyncMock()
        svc = self._build_service(hitl_repo=mock_repo)
        decision = self._make_decision(verdict=DecisionVerdict.APPROVED)

        await svc._route_verdict(decision, self._make_action(), self._make_proposal(), "nl")

        mock_repo.create_hitl_request.assert_not_awaited()

    async def test_hitl_required_tenant_isolatie(self):
        """Tenant A ticket mag niet zichtbaar zijn voor tenant B."""
        call_log: list = []

        async def fake_create(**kwargs) -> str:
            call_log.append(kwargs)
            return f"hitl_{kwargs['tenant_id']}"

        mock_repo_a = AsyncMock()
        mock_repo_a.create_hitl_request = AsyncMock(side_effect=fake_create)
        mock_repo_b = AsyncMock()
        mock_repo_b.create_hitl_request = AsyncMock(side_effect=fake_create)

        svc_a = self._build_service(hitl_repo=mock_repo_a)
        svc_b = self._build_service(hitl_repo=mock_repo_b)

        decision = self._make_decision(verdict=DecisionVerdict.HITL_REQUIRED)
        await svc_a._route_verdict(decision, self._make_action(), self._make_proposal(tenant_id=1), "nl")
        await svc_b._route_verdict(decision, self._make_action(), self._make_proposal(tenant_id=2), "nl")

        assert call_log[0]["tenant_id"] == 1
        assert call_log[1]["tenant_id"] == 2
        assert call_log[0]["tenant_id"] != call_log[1]["tenant_id"]
