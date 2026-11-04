"""
Architecture test: .env.single-tenant.example mag geen CORS wildcard (*) bevatten (FA-002).
"""

from pathlib import Path


def test_env_example_no_cors_wildcard():
    env_file = Path(".env.single-tenant.example")
    assert env_file.exists(), ".env.single-tenant.example ontbreekt"
    content = env_file.read_text(encoding="utf-8")
    assert "CORS_ALLOWED_ORIGINS=*" not in content, (
        ".env.single-tenant.example bevat CORS_ALLOWED_ORIGINS=* -- "
        "wildcard CORS is nooit toegestaan in productie (security.md)"
    )
