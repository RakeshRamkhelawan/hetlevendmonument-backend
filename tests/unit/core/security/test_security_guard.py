from unittest.mock import MagicMock, patch

import pytest

from src.core.security.security_guard import SecurityGuard


@pytest.fixture
def security_guard():
    # Setup mock admin notification callback
    notifier = MagicMock()
    return SecurityGuard(notify_admin_callback=notifier), notifier


@pytest.mark.asyncio
@patch("src.core.security.security_guard.SecurityGuard._fetch_cve_db")
async def test_security_guard_happy_path(mock_fetch, security_guard):
    guard, notifier = security_guard
    # Mock CVE DB with a known vulnerability
    mock_fetch.return_value = {
        "requests": [{"id": "CVE-2023-XXXX", "vulnerable_versions": "<=2.28.1"}]
    }

    skills = [
        {
            "name": "BadSkill",
            "status": "active",
            "dependencies": {"requests": "2.28.0"},  # Vulnerable
        },
        {"name": "GoodSkill", "status": "active", "dependencies": {"requests": "2.31.0"}},  # Safe
    ]

    results = await guard.scan_skills(skills)

    assert results[0]["name"] == "BadSkill"
    assert results[0]["status"] == "Disabled"
    assert "CVE-2023-XXXX" in results[0]["reason"]

    assert results[1]["name"] == "GoodSkill"
    assert results[1]["status"] == "active"

    notifier.assert_called_once()
    assert "BadSkill disabled" in notifier.call_args[0][0]


@pytest.mark.asyncio
@patch("src.core.security.security_guard.SecurityGuard._fetch_cve_db")
async def test_security_guard_unreachable_db(mock_fetch, security_guard):
    guard, notifier = security_guard
    mock_fetch.side_effect = Exception("Connection Timeout")

    skills = [{"name": "TestSkill", "status": "active", "dependencies": {"requests": "2.28.0"}}]

    # Should fallback gracefully
    results = await guard.scan_skills(skills)

    assert results[0]["name"] == "TestSkill"
    assert results[0]["status"] == "active"  # Unchanged because DB was unreachable
    assert "Warning: CVE scan skipped" in results[0].get("warnings", "")


@pytest.mark.asyncio
async def test_security_guard_with_live_default_cve_db(security_guard):
    """Verify that SecurityGuard detects vulnerabilities without any mocking."""
    guard, notifier = security_guard
    skills = [
        {"name": "OldPyYAML", "status": "active", "dependencies": {"pyyaml": "5.3"}},
        {"name": "ModernPyYAML", "status": "active", "dependencies": {"pyyaml": "6.0"}},
    ]
    results = await guard.scan_skills(skills)
    assert results[0]["status"] == "Disabled"
    assert "CVE-2020-14343" in results[0]["reason"]
    assert results[1]["status"] == "active"

