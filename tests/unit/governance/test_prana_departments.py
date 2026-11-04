"""Fase 1 -- canonical governance-owned prana department set + resolver.

Gate-2 C1/C2/M1: governance must NOT import the ALS Department enum (runtime coupling
+ divergent string values like "finance" vs "finance_treasury" + a duplicate OPERATIONS
alias that would split a budget). This module is the single canonical source used for
seeding, resolution and (future) classification.
"""

import pytest

from src.core.governance.prana_departments import (
    DEFAULT_COPILOT_DEPARTMENT,
    PranaDepartment,
    resolve_department,
)


@pytest.mark.unit
def test_canonical_set_has_no_duplicate_operations_alias():
    """C2: exactly one operations department -- no 'operations_supply_chain' alias that
    would create a second 10000 budget row for the same logical department."""
    values = [d.value for d in PranaDepartment]
    assert "operations" in values
    assert "operations_supply_chain" not in values
    # No duplicate values.
    assert len(values) == len(set(values))


@pytest.mark.unit
def test_default_copilot_department_is_valid_member():
    """U3: the fixed fallback must be a real member (the old 'general' was not)."""
    assert isinstance(DEFAULT_COPILOT_DEPARTMENT, PranaDepartment)
    assert DEFAULT_COPILOT_DEPARTMENT == PranaDepartment.CUSTOMER_EXPERIENCE


@pytest.mark.unit
def test_resolve_uses_valid_action_param_department():
    """A valid department in action_params wins."""
    dept = resolve_department("create_task", {"department": "finance"})
    assert dept == PranaDepartment.FINANCE


@pytest.mark.unit
def test_resolve_ignores_invalid_action_param_and_uses_tenant_default():
    """An invalid action_params.department is ignored; the tenant default is used."""
    dept = resolve_department(
        "create_task",
        {"department": "not_a_department"},
        tenant_default=PranaDepartment.HR,
    )
    assert dept == PranaDepartment.HR


@pytest.mark.unit
def test_resolve_falls_back_to_fixed_default():
    """No department anywhere -> the fixed CUSTOMER_EXPERIENCE bucket."""
    assert resolve_department("noop", {}) == PranaDepartment.CUSTOMER_EXPERIENCE
    assert resolve_department("create_task", None) == PranaDepartment.CUSTOMER_EXPERIENCE


@pytest.mark.unit
def test_resolve_rejects_alias_string():
    """C2: the legacy alias string must not resolve (it is not canonical)."""
    assert (
        resolve_department("create_task", {"department": "operations_supply_chain"})
        == PranaDepartment.CUSTOMER_EXPERIENCE
    )
