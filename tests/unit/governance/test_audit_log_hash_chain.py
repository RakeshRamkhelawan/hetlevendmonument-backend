"""TDD: AuditLog hash chain populatie in _create_audit_log() -- SP-DLP-003 Dag 3 (ADR-019)."""

import inspect

from src.core.governance.dsar_service import DSARService


def test_create_audit_log_populates_audit_hash():
    """_create_audit_log() moet audit_hash instellen op het AuditLog entry -- ADR-019."""
    src = inspect.getsource(DSARService._create_audit_log)
    assert "audit_hash" in src, (
        "_create_audit_log() stelt audit_hash niet in -- ADR-019 hash chain niet gepopuleerd"
    )


def test_create_audit_log_sets_previous_hash():
    """_create_audit_log() moet previous_hash koppelen aan vorig entry -- ADR-019."""
    src = inspect.getsource(DSARService._create_audit_log)
    assert "previous_hash" in src, (
        "_create_audit_log() koppelt previous_hash niet -- hash chain niet aaneengesloten"
    )
