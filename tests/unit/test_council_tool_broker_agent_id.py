"""AUDIT-007 regression tests: agent-aware _ToolBrokerAdapter for the Council.

Before the fix, _ToolBrokerAdapter hardcoded "copilot" as the agent_id for
every Council tool allowlist check, so a background agent (e.g. "hr_skill")
was evaluated against the copilot permission profile instead of its own
(ADR-015 least-privilege violation for agent hierarchy governance, ADR-036).

These tests pin the fix:

- _ToolBrokerAdapter accepts an optional agent_id (default "copilot").
- build_council(db, agent_id=...) forwards it to the SecurityOfficer adapter.
  The default path keeps using the module-level singleton (WE-009), so HTTP
  behaviour is byte-for-byte unchanged.
- request_council_decision_for_agent forwards its agent_id to build_council.
- Fail-secure guarantee: a non-copilot agent without a permission profile is
  default-denied (ADR-015), never silently allowed.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.copilot.council.factory import _ToolBrokerAdapter
from src.core.copilot.council.types import (
    CouncilDecision,
    DecisionVerdict,
    ProposalTrigger,
)

pytestmark = pytest.mark.unit


def _make_decision(verdict: DecisionVerdict, tenant_id: int) -> CouncilDecision:
    """Minimal CouncilDecision for background-gate tests."""
    return CouncilDecision(
        proposal_id=uuid4(),
        tenant_id=tenant_id,
        user_id=1,
        verdict=verdict,
        officer_verdicts=(),
        explanation_for_user="test",
        decision_hash="deadbeef",
        previous_decision_hash=None,
        deliberation_ms=1,
    )


def _security_officer_of(council: Any) -> Any:
    """Extract the SecurityOfficer from an AgentCouncil's voting officers."""
    return next(o for o in council._voting_officers if o.name == "SecurityOfficer")


class TestToolBrokerAdapterAgentId:
    """Adapter-level pinning of the agent_id parameter (tests 1.1 and 1.2)."""

    async def test_default_agent_id_is_copilot_for_backwards_compatibility(self) -> None:
        """_ToolBrokerAdapter() without arguments must keep using "copilot".

        Every existing HTTP Council call depends on this default -- changing it
        would silently alter production allowlist behaviour.
        """
        with patch("src.core.copilot.council.factory.ToolPermissionManager") as mgr_cls:
            mgr = mgr_cls.return_value
            mgr.is_tool_allowed.return_value = True

            adapter = _ToolBrokerAdapter()
            allowed = await adapter.is_allowed("some_action", tenant_id=1, user_id=1)

        mgr.is_tool_allowed.assert_called_once_with("copilot", "some_action")
        assert allowed is True

    async def test_explicit_agent_id_is_forwarded_to_permission_manager(self) -> None:
        """_ToolBrokerAdapter(agent_id="hr_skill") must check the hr_skill profile."""
        with patch("src.core.copilot.council.factory.ToolPermissionManager") as mgr_cls:
            mgr = mgr_cls.return_value
            mgr.is_tool_allowed.return_value = True

            adapter = _ToolBrokerAdapter(agent_id="hr_skill")
            allowed = await adapter.is_allowed("some_action", tenant_id=1, user_id=1)

        mgr.is_tool_allowed.assert_called_once_with("hr_skill", "some_action")
        assert allowed is True


class TestBuildCouncilAgentId:
    """build_council wiring of agent_id (tests 1.3 and 1.4)."""

    @asynccontextmanager
    async def _patched_heavy_dependencies(self) -> AsyncGenerator[None, None]:
        """Mock the per-request I/O dependencies of build_council.

        The officer construction itself stays real -- only Redis, the twin
        service chain and the tenant context are replaced, so this test
        exercises the actual wiring under test.
        """
        with (
            patch(
                "src.core.copilot.council.factory._get_redis_safe",
                new=AsyncMock(return_value=None),
            ),
            patch("src.core.copilot.council.factory.TwinConsentManager", new=MagicMock()),
            patch(
                "src.core.copilot.council.factory._create_twin_service",
                new=AsyncMock(return_value=MagicMock()),
            ),
            patch(
                "src.core.copilot.council.factory.require_tenant_id",
                return_value=1,
            ),
            patch(
                "src.core.copilot.council.factory.get_redis_pool",
                return_value=MagicMock(),
            ),
            patch(
                "src.core.database.redis.get_redis_client",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            yield

    async def test_build_council_default_keeps_security_officer_singleton(self) -> None:
        """build_council(db) must reuse the WE-009 module-level singleton.

        This is the HTTP backwards-compatibility guarantee: the default path
        must be identical before and after the AUDIT-007 fix.
        """
        from src.core.copilot.council import factory

        async with self._patched_heavy_dependencies():
            council = await factory.build_council(MagicMock())

        security = _security_officer_of(council)
        assert security is factory._get_security_officer(), (
            "Default build_council must keep reusing the module-level "
            "SecurityOfficer singleton (WE-009); HTTP behaviour must be unchanged."
        )

    async def test_build_council_forwards_agent_id_to_security_adapter(self) -> None:
        """build_council(db, agent_id="hr_skill") builds a fresh, agent-aware officer."""
        from src.core.copilot.council import factory

        async with self._patched_heavy_dependencies():
            council = await factory.build_council(MagicMock(), agent_id="hr_skill")

        security = _security_officer_of(council)
        assert security is not factory._get_security_officer(), (
            "A non-default agent_id must NOT reuse the copilot singleton -- "
            "that would leak the copilot permission profile into agent checks."
        )
        adapter = security._tool_broker
        assert isinstance(adapter, factory._ToolBrokerAdapter)
        assert adapter._agent_id == "hr_skill"


class TestBackgroundGateAgentIdForwarding:
    """background_gate forwarding of agent_id (test 1.5)."""

    async def test_request_council_decision_for_agent_forwards_agent_id(self) -> None:
        """request_council_decision_for_agent must pass agent_id to build_council."""
        from src.core.copilot.council import background_gate

        fake_db = MagicMock()
        fake_council = AsyncMock()
        fake_council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.APPROVED, tenant_id=1)
        )

        @asynccontextmanager
        async def _fake_db_session() -> AsyncGenerator[Any, None]:
            yield fake_db

        with (
            patch.object(background_gate, "get_db_session", _fake_db_session),
            patch.object(
                background_gate,
                "build_council",
                new=AsyncMock(return_value=fake_council),
            ) as build_mock,
        ):
            outcome = await background_gate.request_council_decision_for_agent(
                tenant_id=1,
                agent_id="hr_skill",
                user_id=1,
                action_type="send_notification",
                action_params={},
                reasoning="unit test",
                trigger=ProposalTrigger.PROACTIVE_MONITOR,
            )

        build_mock.assert_awaited_once_with(fake_db, agent_id="hr_skill")
        assert outcome.decision.verdict == DecisionVerdict.APPROVED


class TestFailSecureForUnknownAgent:
    """Behavioral guarantee: agent-aware checks stay fail-secure (ADR-015)."""

    async def test_agent_without_permission_profile_is_default_denied(self) -> None:
        """A non-copilot agent without a profile must be denied, not allowed.

        Uses the real ToolPermissionManager against the repo config: agent
        profiles for ALS skills do not exist yet (AUDIT-008), so "hr_skill"
        resolves to the ADR-015 default-deny. This proves the AUDIT-007 fix
        cannot accidentally widen permissions for unprofiled agents.
        """
        adapter = _ToolBrokerAdapter(agent_id="hr_skill")

        allowed = await adapter.is_allowed("some_action", tenant_id=1, user_id=1)

        assert allowed is False, (
            "Agent 'hr_skill' has no permission profile; ADR-015 default-deny "
            "must apply. If this fails, the adapter is widening permissions."
        )
