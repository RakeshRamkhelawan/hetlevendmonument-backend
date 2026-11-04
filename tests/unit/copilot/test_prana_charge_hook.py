"""Fase 3b -- prana charge-hook in CopilotService._execute_decision.

Charge-before-execute (flag-guarded), fixed copilot department, refund-on-failure.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.copilot.council.types import DecisionVerdict
from src.core.copilot.service import CopilotService
from src.core.governance.prana_service import InsufficientPranaError


def _make_service(prana):
    guard = MagicMock()
    guard.start_execution = AsyncMock(return_value=True)
    guard.finish_execution = AsyncMock()
    audit = MagicMock()
    audit.bind_execution_result = AsyncMock()
    broker = MagicMock()
    broker.execute_tool = AsyncMock(return_value={"ok": True})
    svc = CopilotService(
        council=MagicMock(),
        llm_handler=MagicMock(),
        proposal_builder=MagicMock(),
        tool_broker=broker,
        audit_writer=audit,
        execution_guard=guard,
        prana_service=prana,
    )
    return svc, broker


def _proposal():
    p = MagicMock()
    p.tenant_id = 7
    p.user_id = 5
    p.action_type = "create_task"
    p.action_params = {}
    return p


def _decision():
    d = MagicMock()
    d.verdict = DecisionVerdict.APPROVED
    d.decision_id = uuid4()
    return d


@pytest.mark.unit
async def test_no_charge_when_enforcement_off(monkeypatch):
    monkeypatch.delenv("PRANA_ENFORCEMENT_ENABLED", raising=False)
    prana = MagicMock()
    prana.charge = AsyncMock()
    svc, broker = _make_service(prana)

    await svc._execute_decision(_proposal(), _decision())

    prana.charge.assert_not_called()
    broker.execute_tool.assert_awaited_once()


@pytest.mark.unit
async def test_charges_fixed_department_before_execute_when_on(monkeypatch):
    monkeypatch.setenv("PRANA_ENFORCEMENT_ENABLED", "true")
    prana = MagicMock()
    prana.charge = AsyncMock()
    svc, broker = _make_service(prana)

    await svc._execute_decision(_proposal(), _decision())

    prana.charge.assert_awaited_once()
    args, kwargs = prana.charge.call_args
    assert args[0] == 7 and args[1] == "customer_experience" and args[2] == "create_task"
    assert kwargs["actor_user_id"] == 5
    broker.execute_tool.assert_awaited_once()


@pytest.mark.unit
async def test_insufficient_prana_blocks_execution(monkeypatch):
    monkeypatch.setenv("PRANA_ENFORCEMENT_ENABLED", "true")
    prana = MagicMock()
    prana.charge = AsyncMock(side_effect=InsufficientPranaError("empty"))
    svc, broker = _make_service(prana)

    result = await svc._execute_decision(_proposal(), _decision())

    assert result is None
    broker.execute_tool.assert_not_called()  # denied before the tool runs


@pytest.mark.unit
async def test_refund_when_execution_fails_after_charge(monkeypatch):
    monkeypatch.setenv("PRANA_ENFORCEMENT_ENABLED", "true")
    prana = MagicMock()
    prana.charge = AsyncMock()
    prana.refund = AsyncMock()
    svc, broker = _make_service(prana)
    broker.execute_tool = AsyncMock(side_effect=RuntimeError("tool boom"))

    with pytest.raises(RuntimeError):
        await svc._execute_decision(_proposal(), _decision())

    prana.refund.assert_awaited_once()  # charged then failed -> refunded
