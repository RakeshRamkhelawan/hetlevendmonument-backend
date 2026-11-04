"""PranaGuard (ADR-021) -- flag-on behaviour over the persistent PranaService.

Replaces the pre-fase-2 test that mocked tenants.prana_spent/prana_budget columns which
never existed. PranaGuard now delegates to PranaService; here we mock the service to test
the guard's block/allow decision. The flag-OFF no-op is covered in
test_prana_als_consolidation.py; the real DB behaviour in the integration suite.
"""

from unittest.mock import AsyncMock

import pytest

from src.core.governance import prana_guard as pg
from src.core.governance.prana_guard import InsufficientPranaError, PranaGuard


class _SessionCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *args):
        return False


def _patch_service(monkeypatch, has_budget_result: bool) -> None:
    monkeypatch.setenv("PRANA_ENFORCEMENT_ENABLED", "true")
    monkeypatch.setattr(pg.db_manager, "get_session", lambda: _SessionCtx(AsyncMock()))

    class _Svc:
        def __init__(self, db):
            pass

        async def has_budget(self, *args, **kwargs):
            return has_budget_result

    monkeypatch.setattr(pg, "PranaService", _Svc)


@pytest.mark.unit
async def test_prana_guard_blocks_when_department_budget_exhausted(monkeypatch):
    _patch_service(monkeypatch, has_budget_result=False)
    guard = PranaGuard()
    with pytest.raises(InsufficientPranaError):
        await guard.check_budget(tenant_id=1, department="finance_treasury")


@pytest.mark.unit
async def test_prana_guard_allows_when_budget_available(monkeypatch):
    _patch_service(monkeypatch, has_budget_result=True)
    guard = PranaGuard()
    await guard.check_budget(tenant_id=1, department="finance_treasury")  # no raise
