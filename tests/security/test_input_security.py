import pytest
from fastapi import HTTPException

from src.core.middleware.input_sanitizer import InputSanitizer
from src.core.security.input_sanitization import InjectionProtector, validate_string_input


def test_sql_injection_rejection():
    protector = InjectionProtector()
    payloads = [
        "' OR 1=1 --",
        "'; DROP TABLE users;--",
        "UNION SELECT user, password FROM users",
    ]
    for payload in payloads:
        result = protector.check_sql_injection(payload)
        assert result.is_valid is False, f"Payload {payload} should be rejected"


def test_command_injection_rejection():
    protector = InjectionProtector()
    payloads = ["search; ls -la", "search && whoami", "$(whoami)"]
    for payload in payloads:
        result = protector.check_command_injection(payload)
        assert result.is_valid is False, f"Payload {payload} should be rejected"


def test_input_sanitizer_middleware_logic():
    # Test search query sanitization
    with pytest.raises(HTTPException) as exc:
        InputSanitizer.sanitize_search_query("' OR 1=1 --")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        InputSanitizer.sanitize_search_query("search; ls -la")
    assert exc.value.status_code == 400


def test_xss_protection():
    payloads = [
        "<script>alert('XSS')</script>",
        "javascript:alert(1)",
        "<img src=x onerror=alert(1)>",
    ]
    for payload in payloads:
        with pytest.raises(HTTPException) as exc:
            InputSanitizer.sanitize_text_input(payload)
        assert exc.value.status_code == 400


def test_path_traversal_protection():
    payloads = ["../../etc/passwd", "..\\..\\windows\\win.ini"]
    for payload in payloads:
        with pytest.raises(HTTPException) as exc:
            InputSanitizer.validate_filename(payload)
        assert exc.value.status_code == 400
