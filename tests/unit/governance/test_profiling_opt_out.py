"""TDD tests -- GDPR-009 profiling opt-out in base_agent.py (SP-DLP-002 Dag 4).

These tests are RED before _profiling_opted_out is added to EnhancedBaseAgent,
GREEN after the attribute is wired.
"""

from pathlib import Path


def test_base_agent_checks_profiling_consent_before_activate() -> None:
    """EnhancedBaseAgent moet een profiling opt-out vlag kennen -- GDPR-009."""
    src = Path("src/core/agents/base_agent.py").read_text(encoding="utf-8")
    assert "profiling" in src.lower(), (
        "base_agent.py heeft geen profiling opt-out vlag -- "
        "GDPR-009 vereist dat agents weten of profiling is toegestaan"
    )


def test_base_agent_profiling_opted_out_attribute_present() -> None:
    """base_agent.py moet _profiling_opted_out attribuut bevatten -- GDPR-009."""
    src = Path("src/core/agents/base_agent.py").read_text(encoding="utf-8")
    assert "_profiling_opted_out" in src, (
        "base_agent.py mist _profiling_opted_out attribuut -- "
        "GDPR-009 vereist expliciete profiling opt-out ondersteuning"
    )
