"""GOV-002/003/004 -- no AuditLog write path may bypass the hash chain
(Sprint Dag 1 Groep 2, AUDIT-ARCH-2026-07-02).

In scope today: the two non-canonical AuditService classes (governance/services/
audit_service.py, security/security_audit_service.py) must reference the canonical
HashChainVerifier wherever they construct an AuditLog(...) record.

TODO(SP-GOV-ARCH-5): while verifying this fix, 6 additional modules (8 call-sites --
erasure_router and portability_router each have 2) were discovered that also construct
AuditLog(...) without any hash chain (GDPR erasure/portability routers, compliance PDF
export, billing, Stripe webhook, GDPR purge actor). These are a new, separate finding --
out of scope for Groep 2 (governance-contract + AuditService consolidation) -- and must
be triaged in a follow-up sprint. This test intentionally stays RED until that backlog
is picked up, so it is not silently forgotten.

TODO(SP-GOV-ARCH-5): also discovered -- 3 READ-side call-sites in
src/core/security/security_audit_service.py (get_recent_events, get_security_summary
x2, lines ~522/698/712) still compare AuditLog.tenant_id (Mapped[int]) against
str(tenant_id) -- the identical bug class GOV-004 fixed on the write side in the same
file's log_event()/verify_log_integrity(). Not fixed today (different methods, out of
today's Groep 2 scope) -- see test_read_paths_do_not_compare_tenant_id_as_str below.
"""

import inspect

from src.core.governance.services import audit_service as services_audit_service_module
from src.core.security import security_audit_service as security_audit_service_module

IN_SCOPE_MODULES = [services_audit_service_module, security_audit_service_module]

# TODO(SP-GOV-ARCH-5): backlog -- AuditLog(...) construction sites without any
# hash-chain population, discovered while verifying GOV-002/003/004 today.
BACKLOG_NON_HASH_CHAIN_MODULES = [
    "src.core.actors.gdpr_purge",
    "src.core.api.billing_endpoints",
    "src.core.api.v1.compliance.pdf_router",
    "src.core.api.v1.gdpr_compliance.erasure_router",
    "src.core.api.v1.gdpr_compliance.portability_router",
    "src.core.api.webhooks.stripe_handler",
]


def test_in_scope_audit_services_reference_canonical_hash_chain_verifier() -> None:
    for module in IN_SCOPE_MODULES:
        source = inspect.getsource(module)
        assert "HashChainVerifier" in source, (
            f"{module.__name__} constructs an AuditLog(...) record but no longer "
            "references the canonical HashChainVerifier -- GOV-002/003/004 fix regressed."
        )


def test_in_scope_audit_services_do_not_use_legacy_json_metadata_hash_scheme() -> None:
    security_source = inspect.getsource(security_audit_service_module)
    assert 'event_metadata.get("log_hash")' not in security_source, (
        "security_audit_service.py must not advance its hash chain via JSON "
        "event_metadata -- use HashChainVerifier + audit_hash/previous_hash columns."
    )


def test_backlog_non_hash_chain_audit_writes_are_fixed() -> None:
    """SP-GOV-ARCH-5 (AUDIT-ARCH-2026-07-02 Dag 3 Groep B): these 6 modules used to
    construct AuditLog(...) directly with no hash-chain population at all. Fixed by
    migrating each call-site to governance/audit.py::AuditService.log_action() (the
    canonical hash-chain write path) instead of duplicating a direct HashChainVerifier
    reference in every caller -- so this test accepts either a direct HashChainVerifier
    reference OR a delegation to the canonical AuditService as evidence of the fix."""
    import importlib

    still_missing = []
    for module_name in BACKLOG_NON_HASH_CHAIN_MODULES:
        module = importlib.import_module(module_name)
        source = inspect.getsource(module)
        if "HashChainVerifier" not in source and "AuditService" not in source:
            still_missing.append(module_name)

    assert not still_missing, (
        f"SP-GOV-ARCH-5 backlog not yet resolved -- modules still writing AuditLog "
        f"without hash-chain protection: {still_missing}"
    )


def test_read_paths_do_not_compare_tenant_id_as_str() -> None:
    """TODO(SP-GOV-ARCH-5): security_audit_service.py has 3 read-side call-sites
    (get_recent_events, get_security_summary x2) that still filter
    AuditLog.tenant_id (Mapped[int]) against str(tenant_id) -- the same bug class
    GOV-004 fixed on the write side (log_event) and the read side (verify_log_integrity)
    in the same file, discovered 2026-07-02. Intentionally RED until fixed."""
    source = inspect.getsource(security_audit_service_module)
    assert "AuditLog.tenant_id == str(tenant_id)" not in source, (
        "SP-GOV-ARCH-5 backlog not yet resolved -- security_audit_service.py still "
        "compares AuditLog.tenant_id against str(tenant_id) in a read path."
    )
