"""Fase 5 -- /prana/budgets + /prana/allocate handler logic.

The PRANA_MANAGE/PRANA_READ scope gating is enforced by require_scopes (covered by the auth
suite) and asserted structurally by tests/architecture/test_prana_emergency_scope_gated.py.
Here we test the handler logic directly (mocked PranaService), in particular that
allocate uses the verified caller id for authorized_by -- never a client-supplied value.
"""

from unittest.mock import AsyncMock

import pytest

from src.core.api.v1 import prana


@pytest.mark.unit
async def test_get_prana_budgets_returns_department_entries(monkeypatch):
    class _Budget:
        def __init__(self, dept, total, spent):
            self.department = dept
            self.total_prana = total
            self.spent_prana = spent

    class _Svc:
        def __init__(self, db):
            pass

        async def get_balances(self, tenant_id):
            assert tenant_id == 7
            return [_Budget("finance", 10000, 200)]

    # prana.py haalt PranaService dynamisch op via importlib (ADR-033, geen directe
    # governance-import in de API-laag) -- patchen op de bronmodule, niet op `prana` zelf.
    monkeypatch.setattr("src.core.governance.prana_service.PranaService", _Svc)
    resp = await prana.get_prana_budgets(db=object(), tenant_id=7, _user_id=5)
    assert resp.tenant_id == 7
    assert resp.budgets[0].department == "finance"
    assert resp.budgets[0].available == 9800


@pytest.mark.unit
async def test_allocate_emergency_uses_verified_caller_id(monkeypatch):
    captured = {}

    class _Result:
        department = "finance"
        balance_after = 10500

    class _Svc:
        def __init__(self, db):
            pass

        async def allocate_emergency(self, tenant_id, department, amount, authorized_by, reason):
            captured.update(
                tenant_id=tenant_id,
                department=department,
                amount=amount,
                authorized_by=authorized_by,
                reason=reason,
            )
            return _Result()

    # prana.py haalt PranaService dynamisch op via importlib (ADR-033, geen directe
    # governance-import in de API-laag) -- patchen op de bronmodule, niet op `prana` zelf.
    monkeypatch.setattr("src.core.governance.prana_service.PranaService", _Svc)
    body = prana.EmergencyAllocationRequest(department="finance", amount=500, reason="topup")
    resp = await prana.allocate_emergency_prana(
        body=body, db=AsyncMock(), tenant_id=7, authorized_by=9
    )
    assert resp.success and resp.amount == 500 and resp.balance_after == 10500
    # authorized_by comes from the scope dependency (id 9), NOT from the request body.
    assert captured["authorized_by"] == 9 and captured["tenant_id"] == 7
