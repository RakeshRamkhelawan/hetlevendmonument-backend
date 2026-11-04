"""
Architecture test: AuditLoggingMiddleware MOET geregistreerd zijn in middleware_config.py.
RED voor de fix (indien afwezig), GREEN na de fix (en als regressieblokkering).
SP-SEC-001 GOV-001
"""

from pathlib import Path


def test_audit_middleware_is_imported_in_config():
    """AuditLoggingMiddleware MOET geregistreerd zijn in middleware_config.py -- SP-SEC-001 GOV-001."""
    config_path = Path("src/core/api/setup/middleware_config.py")
    assert config_path.exists(), "middleware_config.py niet gevonden"

    source = config_path.read_text(encoding="utf-8")
    assert "AuditLoggingMiddleware" in source, (
        "AuditLoggingMiddleware ontbreekt in middleware_config.py. "
        "Voeg de middleware toe aan de ASGI-stack (SP-SEC-001 GOV-001)."
    )


def test_audit_middleware_is_registered_via_add_middleware():
    """AuditLoggingMiddleware moet via add_middleware() geregistreerd zijn -- SP-SEC-001 GOV-001."""
    config_path = Path("src/core/api/setup/middleware_config.py")
    source = config_path.read_text(encoding="utf-8")

    lines = source.splitlines()
    found = False
    for i, line in enumerate(lines):
        if "AuditLoggingMiddleware" in line and "add_middleware" in lines[max(0, i - 3) : i + 3]:
            found = True
            break
        if "add_middleware" in line and "AuditLoggingMiddleware" in line:
            found = True
            break

    # Check surrounding context: add_middleware call near AuditLoggingMiddleware mention
    audit_idx = [
        i
        for i, line in enumerate(lines)
        if "AuditLoggingMiddleware" in line and "import" not in line
    ]
    add_mw_idx = [i for i, line in enumerate(lines) if "add_middleware" in line]

    for ai in audit_idx:
        for mi in add_mw_idx:
            if abs(ai - mi) <= 4:
                found = True
                break

    assert found, (
        "AuditLoggingMiddleware is geimporteerd maar niet via add_middleware() geregistreerd. "
        "Voeg 'app.add_middleware(AuditLoggingMiddleware, ...)' toe (SP-SEC-001 GOV-001)."
    )
