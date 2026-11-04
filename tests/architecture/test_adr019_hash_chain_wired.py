"""ADR-019: governance/ AuditLog writers moeten audit_hash + previous_hash populeren."""

import inspect
from pathlib import Path


def test_dsar_service_audit_hash_wired():
    """dsar_service._create_audit_log() -- GREEN (SP-DLP-003 Dag 3)."""
    from src.core.governance.dsar_service import DSARService

    src = inspect.getsource(DSARService._create_audit_log)
    assert "audit_hash" in src


def test_audit_service_log_action_hash_wired():
    """audit.log_action() -- GREEN (SP-DLP-003 Dag 4)."""
    from src.core.governance.audit import AuditService

    src = inspect.getsource(AuditService.log_action)
    assert "audit_hash" in src


def test_ai_transparency_service_audit_hash_wired():
    """ai_transparency_service.py -- TODO(SP-DLP-004): 3 inserts zonder hash chain."""
    src = Path("src/core/governance/ai_transparency_service.py").read_text(encoding="utf-8")
    # 3 AuditLog inserts op lines ~299, 370, 488 -- nog niet gefixed
    assert "AuditLog(" not in src or "audit_hash" in src, (
        "ai_transparency_service.py heeft AuditLog inserts zonder audit_hash -- SP-DLP-004 backlog"
    )


def test_cookie_consent_audit_hash_wired():
    """cookie_consent.py -- TODO(SP-DLP-004): 1 insert zonder hash chain."""
    src = Path("src/core/governance/cookie_consent.py").read_text(encoding="utf-8")
    assert "AuditLog(" not in src or "audit_hash" in src, (
        "cookie_consent.py heeft een AuditLog insert zonder audit_hash -- SP-DLP-004 backlog"
    )


def test_request_human_review_audit_has_real_tenant_id():
    """request_human_review audit entry hardcodes tenant_id=0 -- TODO(SP-DLP-005): fix bug."""
    src = Path("src/core/governance/ai_transparency_service.py").read_text(encoding="utf-8")
    assert "tenant_id=0,  # Will be filled" not in src, (
        "request_human_review audit entry heeft tenant_id=0 hardcoded (pre-existing bug) -- "
        "SP-DLP-005 backlog: resolve tenant_id vanuit de decision record"
    )
