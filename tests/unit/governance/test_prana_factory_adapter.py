"""Fase 3a -- the Council's prana adapter (factory._PranaServiceAdapter).

Flag OFF (default) -> True (copilot unchanged). Flag ON -> delegates to the real
PranaService with the FIXED copilot department (never the LLM action_params).
"""

import pytest


@pytest.mark.unit
async def test_adapter_returns_true_when_enforcement_off(monkeypatch):
    monkeypatch.delenv("PRANA_ENFORCEMENT_ENABLED", raising=False)
    from src.core.copilot.council.factory import _PranaServiceAdapter

    adapter = _PranaServiceAdapter(db=object())  # db unused when enforcement is off
    assert await adapter.has_budget(1, "create_task") is True


@pytest.mark.unit
async def test_adapter_delegates_with_fixed_department_when_on(monkeypatch):
    monkeypatch.setenv("PRANA_ENFORCEMENT_ENABLED", "true")
    from src.core.copilot.council.factory import _PranaServiceAdapter

    captured = {}

    class _FakeSvc:
        def __init__(self, db):
            pass

        async def has_budget(self, tenant_id, department, action_type):
            captured["args"] = (tenant_id, department, action_type)
            return True

    monkeypatch.setattr("src.core.governance.prana_service.PranaService", _FakeSvc)

    adapter = _PranaServiceAdapter(db=object())
    assert await adapter.has_budget(7, "create_task") is True
    # Fixed copilot bucket -- never derived from LLM action_params.
    assert captured["args"] == (7, "customer_experience", "create_task")
