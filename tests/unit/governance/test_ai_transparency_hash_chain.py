"""TDD: AITransparencyService en CookieConsentManager moeten audit_hash populeren (ADR-019)."""

import inspect

from src.core.governance.ai_transparency_service import AITransparencyService
from src.core.governance.cookie_consent import CookieConsentManager


def test_ai_transparency_service_has_populate_hash_chain():
    assert hasattr(AITransparencyService, "_populate_hash_chain"), (
        "AITransparencyService mist _populate_hash_chain() -- ADR-019 niet gewired"
    )


def test_ai_transparency_service_populate_hash_chain_sets_audit_hash():
    src = inspect.getsource(AITransparencyService._populate_hash_chain)
    assert "audit_hash" in src, (
        "_populate_hash_chain() zet audit_hash niet -- ADR-019 hash chain niet gewired"
    )


def test_cookie_consent_update_consent_sets_audit_hash():
    src = inspect.getsource(CookieConsentManager.update_consent)
    assert "audit_hash" in src, (
        "update_consent() zet audit_hash niet -- ADR-019 hash chain niet gewired"
    )


def test_request_human_review_resolves_tenant_id_from_decision():
    src = inspect.getsource(AITransparencyService.request_human_review)
    assert "AIDecision.tenant_id" in src, (
        "request_human_review() zoekt tenant_id niet op uit AIDecision -- SP-DLP-005"
    )
