"""TDD: AuditService.log_action() moet audit_hash + previous_hash populeren (ADR-019)."""

import inspect

from src.core.governance.audit import AuditService


def test_log_action_populates_audit_hash():
    src = inspect.getsource(AuditService.log_action)
    assert "audit_hash" in src, (
        "log_action() zet audit_hash niet -- ADR-019 hash chain niet gewired"
    )


def test_log_action_sets_previous_hash():
    src = inspect.getsource(AuditService.log_action)
    assert "previous_hash" in src, (
        "log_action() zet previous_hash niet -- ADR-019 hash chain niet gewired"
    )
