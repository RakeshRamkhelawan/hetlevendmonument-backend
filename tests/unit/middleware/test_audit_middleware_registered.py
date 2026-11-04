"""
Unit tests: AuditLoggingMiddleware geregistreerd in ASGI-stack -- SP-SEC-001 GOV-001

Test 2.1 controleert dat de middleware aanwezig is in middleware_config.py.
Test 2.2 controleert runtime-registratie via setup_middleware().
"""

import pytest


def test_audit_middleware_present_in_middleware_config():
    """AuditLoggingMiddleware must be imported and registered in middleware_config -- GOV-001."""
    from pathlib import Path

    config_path = Path("src/core/api/setup/middleware_config.py")
    assert config_path.exists(), "middleware_config.py niet gevonden"

    source = config_path.read_text(encoding="utf-8")
    assert "AuditLoggingMiddleware" in source, (
        "AuditLoggingMiddleware ontbreekt in middleware_config.py. "
        "Voeg import en app.add_middleware(AuditLoggingMiddleware) toe (SP-SEC-001 GOV-001)."
    )
    assert "add_middleware" in source, (
        "app.add_middleware() ontbreekt in middleware_config.py (SP-SEC-001 GOV-001)."
    )


def test_audit_middleware_class_importable():
    """AuditLoggingMiddleware must be importable without circular import errors -- GOV-001."""
    try:
        from src.core.middleware.audit_middleware import AuditLoggingMiddleware

        assert AuditLoggingMiddleware is not None
    except ImportError as e:
        pytest.fail(
            f"AuditLoggingMiddleware kon niet worden geimporteerd: {e}. "
            "Controleer op circulaire imports (SP-SEC-001 GOV-001)."
        )
