"""SP-WE-05: EthicsOfficer can_veto MVP decision tests."""

import pytest


@pytest.mark.unit
class TestEthicsOfficerVetoDecision:
    def test_ethics_officer_can_veto_is_false_mvp(self) -> None:
        """can_veto=False is the deliberate MVP choice per ADR-027 §5.2.5."""
        from src.core.copilot.council.members.ethics_officer import EthicsOfficer

        assert EthicsOfficer.can_veto is False

    def test_ethics_officer_allowed_verdicts_excludes_veto(self) -> None:
        """EthicsOfficer cannot structurally emit VETO (allowed_verdicts check)."""
        from src.core.copilot.council.members.ethics_officer import EthicsOfficer
        from src.core.copilot.council.types import VerdictType

        assert VerdictType.VETO not in EthicsOfficer.allowed_verdicts

    def test_ethics_officer_docstring_documents_mvp_decision(self) -> None:
        """Class docstring contains MVP decision explanation."""
        from src.core.copilot.council.members.ethics_officer import EthicsOfficer

        doc = EthicsOfficer.__doc__ or ""
        assert "MVP" in doc

    def test_adr_027_changelog_has_ethics_officer_v16_entry(self) -> None:
        """ADR-027 Changelog v1.6 documents the EthicsOfficer can_veto decision."""
        with open("docs/adr/027-copilot-agent-council.md", encoding="utf-8") as f:
            content = f.read()
        assert "1.6" in content
        assert "WE-007" in content or "can_veto" in content

    def test_claude_md_valkuil_ethics_officer(self) -> None:
        """Valkuilen-skill bevat EthicsOfficer can_veto waarschuwing.

        Content was moved from inline CLAUDE.md to .claude/skills/valkuilen/SKILL.md
        when valkuilen were extracted into a dedicated skill (SP-API-008 cleanup).
        CLAUDE.md still references the skill via '5. Valkuilen -- zie .claude/skills/valkuilen/'.
        """
        with open(".claude/skills/valkuilen/SKILL.md", encoding="utf-8") as f:
            content = f.read()
        assert "EthicsOfficer" in content and "can_veto" in content
