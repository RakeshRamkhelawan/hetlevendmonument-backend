"""SEC-010+BE-006+007+ARCH-001+002: CVA chat endpoints MOETEN cva_chat_limit gebruiken.

Rode tests:
- POST /chat en /chat/stream gebruiken cva_chat_limit (niet consent_update_limit)
- ADR-033: governance import verwijderd uit chat_router.py
- GET /conversations heeft een rate limit decorator
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]


class TestCVARateLimitDecorator:
    """CVA endpoints moeten de juiste rate limiters gebruiken (SEC-010 + ADR-033)."""

    def test_chat_router_does_not_import_governance_rate_limiter_directly(self):
        """chat_router.py mag NIET direct src.core.governance.rate_limiter importeren (ADR-033).

        Rate limiter moet via src.core.api.v1.cva.dependencies facade lopen.
        """
        source = (_REPO_ROOT / "src/core/api/v1/cva/chat_router.py").read_text(encoding="utf-8")
        assert "from src.core.governance.rate_limiter" not in source, (
            "chat_router.py importeert direct uit src.core.governance.rate_limiter. "
            "ADR-033: governance imports in router.py zijn verboden. "
            "Fix: voeg cva_chat_limit toe aan dependencies.py en importeer vandaar."
        )

    def test_chat_endpoint_uses_cva_chat_limit_not_consent_update_limit(self):
        """POST /chat MOET @cva_chat_limit gebruiken, NIET @consent_update_limit (SEC-010)."""
        source = (_REPO_ROOT / "src/core/api/v1/cva/chat_router.py").read_text(encoding="utf-8")
        assert "cva_chat_limit" in source, (
            "chat_router.py bevat geen cva_chat_limit decorator. "
            "SEC-010: POST /chat endpoint moet @cva_chat_limit hebben (30/min)."
        )
        assert "consent_update_limit" not in source, (
            "chat_router.py gebruikt nog steeds consent_update_limit op CVA chat endpoints. "
            "SEC-010: vervang door cva_chat_limit (30/min i.p.v. 10/min consent limiet)."
        )

    def test_cva_chat_limit_defined_in_rate_limiter(self):
        """cva_chat_limit MOET gedefinieerd zijn in rate_limiter.py (SEC-010)."""
        source = (_REPO_ROOT / "src/core/governance/rate_limiter.py").read_text(encoding="utf-8")
        assert "def cva_chat_limit" in source, (
            "src/core/governance/rate_limiter.py bevat geen cva_chat_limit definitie. "
            "SEC-010: voeg cva_chat_limit toe (30 requests per minute)."
        )

    def test_cva_chat_limit_exported_from_dependencies(self):
        """cva_chat_limit MOET geexporteerd zijn via dependencies.py (ADR-033 facade)."""
        source = (_REPO_ROOT / "src/core/api/v1/cva/dependencies.py").read_text(encoding="utf-8")
        assert "cva_chat_limit" in source, (
            "src/core/api/v1/cva/dependencies.py exporteert cva_chat_limit niet. "
            "ADR-033: voeg cva_chat_limit toe aan de dependencies facade."
        )

    def test_conversations_router_has_rate_limit(self):
        """GET /conversations MOET een rate limit decorator hebben (BE-006)."""
        source = (_REPO_ROOT / "src/core/api/v1/cva/conversations_router.py").read_text(
            encoding="utf-8"
        )
        has_rate_limit = any(
            limiter in source
            for limiter in (
                "cva_chat_limit",
                "consent_read_limit",
                "privacy_rate_limit",
                "rate_limit",
            )
        )
        assert has_rate_limit, (
            "conversations_router.py heeft geen rate limit decorator op GET /conversations. "
            "BE-006: voeg @cva_chat_limit toe aan list_conversations."
        )
