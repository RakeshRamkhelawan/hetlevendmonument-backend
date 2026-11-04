"""
Unit tests for ProposalBuilder.

Test taxonomy per CLAUDE.md kwaliteitsloop:
    - Happy paths      (normal action → INTERNAL)
    - Security paths   (PII action → RESTRICTED)
    - Edge cases       (action=None → PUBLIC)

Markers:
    @pytest.mark.unit
    @pytest.mark.security
"""

from __future__ import annotations

import pytest

from src.core.copilot.council.types import DataClassification, ProposalTrigger
from src.core.copilot.proposal_builder import ProposalBuilder
from src.core.copilot.schemas import CopilotAction


@pytest.mark.unit
@pytest.mark.security
class TestProposalBuilder:
    """Proposal construction and classification rules."""

    def test_build_returns_proposal_with_correct_tenant_and_user(self) -> None:
        builder = ProposalBuilder()
        action = CopilotAction(
            message="Hello",
            action="navigate",
            action_params={"page": "home"},
            confidence=0.9,
            reasoning="User asked for home",
        )
        proposal = builder.build(
            tenant_id=42,
            user_id=7,
            action=action,
            trigger=ProposalTrigger.USER_REQUEST,
            model_id="deepseek-chat",
            model_version="v3.1",
            context_snapshot={"page": "dashboard"},
        )
        assert proposal.tenant_id == 42
        assert proposal.user_id == 7
        assert proposal.action_type == "navigate"
        assert proposal.model_id == "deepseek-chat"
        assert proposal.context_snapshot == {"page": "dashboard"}

    def test_classifies_pii_actions_as_restricted(self) -> None:
        builder = ProposalBuilder()
        for prefix in ("export_data", "share_file", "send_email"):
            action = CopilotAction(
                message="Do it",
                action=prefix,
                action_params={},
                confidence=0.5,
                reasoning="Test",
            )
            proposal = builder.build(
                tenant_id=1,
                user_id=1,
                action=action,
                trigger=ProposalTrigger.USER_REQUEST,
                model_id="m",
                model_version="v1",
                context_snapshot={},
            )
            assert proposal.data_classification == DataClassification.RESTRICTED, (
                f"Expected RESTRICTED for action={prefix}"
            )

    def test_classifies_restricted_param_key_as_restricted(self) -> None:
        builder = ProposalBuilder()
        for key in ("email", "phone", "ssn", "iban", "passport", "bsn", "health_record"):
            action = CopilotAction(
                message="Do it",
                action="update_profile",
                action_params={key: "value"},
                confidence=0.5,
                reasoning="Test",
            )
            proposal = builder.build(
                tenant_id=1,
                user_id=1,
                action=action,
                trigger=ProposalTrigger.USER_REQUEST,
                model_id="m",
                model_version="v1",
                context_snapshot={},
            )
            assert proposal.data_classification == DataClassification.RESTRICTED, (
                f"Expected RESTRICTED for param key={key}"
            )

    def test_classifies_normal_action_as_internal(self) -> None:
        builder = ProposalBuilder()
        action = CopilotAction(
            message="Hello",
            action="navigate",
            action_params={"page": "home"},
            confidence=0.9,
            reasoning="User asked for home",
        )
        proposal = builder.build(
            tenant_id=1,
            user_id=1,
            action=action,
            trigger=ProposalTrigger.USER_REQUEST,
            model_id="m",
            model_version="v1",
            context_snapshot={},
        )
        assert proposal.data_classification == DataClassification.INTERNAL

    def test_action_none_classifies_as_public(self) -> None:
        builder = ProposalBuilder()
        action = CopilotAction(
            message="Hello",
            action=None,
            action_params={},
            confidence=0.9,
            reasoning="Greeting",
        )
        proposal = builder.build(
            tenant_id=1,
            user_id=1,
            action=action,
            trigger=ProposalTrigger.USER_REQUEST,
            model_id="m",
            model_version="v1",
            context_snapshot={},
        )
        assert proposal.data_classification == DataClassification.PUBLIC

    def test_context_snapshot_passes_through_to_proposal(self) -> None:
        builder = ProposalBuilder()
        snapshot = {"route": "/dashboard", "recent_actions": ["view_report"]}
        action = CopilotAction(
            message="Hello",
            action=None,
            action_params={},
            confidence=0.5,
            reasoning="Test",
        )
        proposal = builder.build(
            tenant_id=1,
            user_id=1,
            action=action,
            trigger=ProposalTrigger.USER_REQUEST,
            model_id="m",
            model_version="v1",
            context_snapshot=snapshot,
        )
        assert proposal.context_snapshot == snapshot
