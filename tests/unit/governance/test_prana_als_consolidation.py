"""Fase 3c -- ALS PranaGuard consolidation.

The ALS DepartmentType (divergent values like "finance_treasury") maps to the canonical
PranaDepartment, and PranaGuard is a flag-guarded no-op when enforcement is off (which also
stops the old latent-broken tenants.prana_* column reads).
"""

import pytest

from src.core.governance.prana_departments import PranaDepartment, prana_department_for_als


@pytest.mark.unit
def test_als_department_type_maps_to_canonical_prana_department():
    assert prana_department_for_als("finance_treasury") == PranaDepartment.FINANCE
    assert prana_department_for_als("hr_culture") == PranaDepartment.HR
    assert prana_department_for_als("strategy_business") == PranaDepartment.STRATEGY
    assert prana_department_for_als("operations_supply_chain") == PranaDepartment.OPERATIONS
    assert prana_department_for_als("it_security") == PranaDepartment.IT_SECURITY


@pytest.mark.unit
def test_als_department_unknown_and_none_fall_back_to_operations():
    assert prana_department_for_als(None) == PranaDepartment.OPERATIONS
    assert prana_department_for_als("unassigned") == PranaDepartment.OPERATIONS


@pytest.mark.unit
def test_als_department_accepts_the_real_department_type_enum():
    """specialist_base passes the DepartmentType enum member (a str-enum) directly."""
    from src.core.als.agents.departments.base_department_agent import DepartmentType

    assert prana_department_for_als(DepartmentType.FINANCE_TREASURY) == PranaDepartment.FINANCE
    assert (
        prana_department_for_als(DepartmentType.CUSTOMER_EXPERIENCE)
        == PranaDepartment.CUSTOMER_EXPERIENCE
    )


@pytest.mark.unit
async def test_prana_guard_is_noop_when_enforcement_off(monkeypatch):
    """With the flag off, PranaGuard must not touch the DB (no-op allow) -- this is what
    stops the old latent-broken column reads."""
    monkeypatch.delenv("PRANA_ENFORCEMENT_ENABLED", raising=False)
    from src.core.governance import prana_guard as pg

    def _boom(*args, **kwargs):
        raise AssertionError("db_manager.get_session must not be called when enforcement is off")

    monkeypatch.setattr(pg.db_manager, "get_session", _boom)
    guard = pg.PranaGuard()
    # Neither raises, neither touches the DB.
    await guard.check_budget(1, department="finance_treasury")
    await guard.charge_prana(1, department="finance_treasury")
