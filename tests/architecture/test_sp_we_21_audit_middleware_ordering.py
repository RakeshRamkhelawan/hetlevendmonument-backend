"""SP-WE-21: AuditLoggingMiddleware registratievolgorde regression guard.

In Starlette is de volgorde LIFO: last added = outermost = runs first.
TenantMiddleware moet AFTER AuditLoggingMiddleware geregistreerd staan zodat
TenantMiddleware de outermost is en tenant context altijd zet voordat
AuditLoggingMiddleware het leest.
"""

from pathlib import Path


def test_tenant_middleware_registered_after_audit_middleware() -> None:
    """SP-WE-21: TenantMiddleware moet AFTER AuditLoggingMiddleware staan (LIFO correctheid)."""
    source = Path("src/core/api/setup/middleware_config.py").read_text(encoding="utf-8")
    # Zoek de add_middleware aanroepen -- AuditLoggingMiddleware is een multiline call
    audit_call_pos = source.find("AuditLoggingMiddleware,")
    tenant_call_pos = source.find("app.add_middleware(TenantMiddleware)")
    assert audit_call_pos != -1, "AuditLoggingMiddleware add_middleware call niet gevonden"
    assert tenant_call_pos != -1, "TenantMiddleware add_middleware call niet gevonden"
    assert tenant_call_pos > audit_call_pos, (
        "SP-WE-21: TenantMiddleware moet AFTER AuditLoggingMiddleware geregistreerd worden. "
        "Starlette LIFO: last added = outermost = runs first. "
        "TenantMiddleware moet tenant context zetten voor AuditLoggingMiddleware het leest."
    )


def test_audit_middleware_db_session_factory_passed() -> None:
    """SP-WE-21: db_session_factory moet meegegeven worden aan AuditLoggingMiddleware."""
    source = Path("src/core/api/setup/middleware_config.py").read_text(encoding="utf-8")
    assert "db_session_factory=get_db_session" in source, (
        "SP-WE-21: db_session_factory niet meegegeven -- DB audit logging uitgeschakeld."
    )
