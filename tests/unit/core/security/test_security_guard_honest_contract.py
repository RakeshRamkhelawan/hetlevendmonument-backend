"""Tests for SecurityGuard honest contract and documentation."""

from __future__ import annotations

from pathlib import Path
import pytest

from src.core.security.security_guard import SecurityGuard


SECURITY_GUARD_PATH = Path("src/core/security/security_guard.py")


def test_security_guard_has_todo_security_marker() -> None:
    """_DEFAULT_CVE_DB must have explicit # TODO(SECURITY) marker."""
    content = SECURITY_GUARD_PATH.read_text(encoding="utf-8")
    assert "# TODO(SECURITY):" in content
    assert "pip-audit" in content


@pytest.mark.asyncio
async def test_security_guard_scan_skills_includes_ci_audit_notice() -> None:
    """scan_skills must include explicit note/warning that in-process scanning is a stub and real audits run via pip-audit in CI."""
    guard = SecurityGuard()
    skills = [
        {"name": "SkillA", "status": "active", "dependencies": {"requests": "2.31.0"}}
    ]

    results = await guard.scan_skills(skills)
    assert len(results) == 1
    # Must contain warning or notice about stub nature and CI pip-audit
    assert "pip-audit" in results[0].get("audit_notice", "") or "pip-audit" in results[0].get("warnings", "")
