"""TDD tests for user_management_endpoints type fixes (B2.4).

log_action must receive int tenant_id (not str).
"""

import inspect


def test_log_action_expects_int_tenant_id():
    """log_action signature must declare tenant_id as int."""
    from src.core.governance.audit import AuditService

    sig = inspect.signature(AuditService.log_action)
    tenant_param = sig.parameters["tenant_id"]
    assert (
        tenant_param.annotation is int
        or str(tenant_param.annotation) == "<class 'int'>"
        or "int" in str(tenant_param.annotation)
    ), f"tenant_id annotation is {tenant_param.annotation!r}, expected int or int | None"
