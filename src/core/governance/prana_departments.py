"""Canonical governance-owned prana department set (ADR-021).

Gate-2 (C1/C2/M1): governance defines its OWN department enum instead of importing the
ALS ``Department`` enum. Reasons:
- Importing ``src.core.als...department_orchestrator`` from a governance model would create
  a runtime governance->als coupling loaded very early (alembic env, most imports) and drag
  in signal_bus / organism_registry.
- The ALS enum has divergent string values elsewhere (``DepartmentType`` uses
  "finance_treasury" where ``Department`` uses "finance"), which would make budget lookups
  miss and charge the wrong bucket.
- The ALS enum carries a duplicate ``OPERATIONS_SUPPLY_CHAIN`` alias that would split one
  logical department into two 10000-prana budget rows.

This module is the single source of truth for seeding, resolution and classification.
"""

from __future__ import annotations

from enum import Enum


class PranaDepartment(str, Enum):
    """The canonical 16:9 departments a tenant is funded for (ADR-021).

    One entry per logical department -- deliberately NO ``operations_supply_chain`` alias.
    ``str, Enum`` so the value is a plain string for DB storage and JSON.
    """

    STRATEGY = "strategy"
    OPERATIONS = "operations"
    FINANCE = "finance"
    HR = "hr"
    SALES_MARKETING = "sales_marketing"
    PRODUCT_INNOVATION = "product_innovation"
    IT_SECURITY = "it_security"
    LEGAL_COMPLIANCE = "legal_compliance"
    CUSTOMER_EXPERIENCE = "customer_experience"
    DATA_AI_GOVERNANCE = "data_ai_governance"


# The set seeded per tenant at provisioning (one 10000-prana budget row each).
CANONICAL_DEPARTMENTS: frozenset[PranaDepartment] = frozenset(PranaDepartment)

# U3: fixed fallback for copilot actions that carry no (valid) department. The copilot is
# a customer-facing assistant, so its default bucket is CUSTOMER_EXPERIENCE. This is a real
# member (the previous ai_act adapter fell back to the invalid string "general").
DEFAULT_COPILOT_DEPARTMENT: PranaDepartment = PranaDepartment.CUSTOMER_EXPERIENCE


def _coerce(value: object) -> PranaDepartment | None:
    """Return the matching PranaDepartment for a string value, else None."""
    if isinstance(value, PranaDepartment):
        return value
    if isinstance(value, str):
        try:
            return PranaDepartment(value)
        except ValueError:
            return None
    return None


def resolve_department(
    action_type: str,
    action_params: dict[str, object] | None,
    tenant_default: PranaDepartment | None = None,
) -> PranaDepartment:
    """Resolve the department a copilot action charges against.

    Order (Gate-2 U3): a valid ``action_params["department"]`` -> the tenant default ->
    the fixed ``DEFAULT_COPILOT_DEPARTMENT``. An invalid/legacy-alias string is ignored,
    never trusted as a scope. ``action_type`` is accepted for future classification but is
    not yet used to pick a department.
    """
    if action_params:
        from_params = _coerce(action_params.get("department"))
        if from_params is not None:
            return from_params
    if tenant_default is not None:
        return tenant_default
    return DEFAULT_COPILOT_DEPARTMENT


# ALS `DepartmentType` (src/core/als/agents/departments/base_department_agent.py) uses
# DIVERGENT string values ("finance_treasury" vs prana "finance"). This map is the single
# translation from an ALS department to the canonical prana department, so the ALS path
# and the copilot path charge the SAME budget rows.
_DEPARTMENT_TYPE_TO_PRANA: dict[str, PranaDepartment] = {
    "product_innovation": PranaDepartment.PRODUCT_INNOVATION,
    "operations_supply_chain": PranaDepartment.OPERATIONS,
    "sales_marketing": PranaDepartment.SALES_MARKETING,
    "finance_treasury": PranaDepartment.FINANCE,
    "hr_culture": PranaDepartment.HR,
    "it_security": PranaDepartment.IT_SECURITY,
    "legal_compliance": PranaDepartment.LEGAL_COMPLIANCE,
    "customer_experience": PranaDepartment.CUSTOMER_EXPERIENCE,
    "strategy_business": PranaDepartment.STRATEGY,
    "data_ai_governance": PranaDepartment.DATA_AI_GOVERNANCE,
}

# ALS agents without a mapped department (e.g. "unassigned") charge the operations bucket.
_ALS_DEFAULT_DEPARTMENT = PranaDepartment.OPERATIONS


def prana_department_for_als(department_type_value: str | None) -> PranaDepartment:
    """Translate an ALS DepartmentType string value to the canonical PranaDepartment."""
    if not department_type_value:
        return _ALS_DEFAULT_DEPARTMENT
    return _DEPARTMENT_TYPE_TO_PRANA.get(department_type_value, _ALS_DEFAULT_DEPARTMENT)
