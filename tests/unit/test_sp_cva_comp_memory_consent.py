"""COMP-002 + COMP-007: _write_memory_candidate() moet consent checken voor schrijven.

GDPR Art. 6 -- episodisch geheugen schrijven vereist PERSONALIZATION consent.
Tests zijn ROOD totdat Fix B is geimplementeerd.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWriteMemoryCandidateConsent:
    """_write_memory_candidate() moet PERSONALIZATION consent valideren voor schrijven."""

    @pytest.mark.asyncio
    async def test_memory_write_skipped_when_no_personalization_consent(self):
        """Geen memory write als PERSONALIZATION consent ontbreekt (SP-CVA-COMP-002)."""
        from src.core.services.cva_service import _write_memory_candidate

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        @MagicMock
        def db_factory():
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _ctx():
                yield mock_session

            return _ctx()

        with (
            patch(
                "src.core.governance.cookie_consent.CookieConsentManager.is_consent_given",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "src.domains.memory.services.memory_write_service.MemoryWriteService.write",
                new_callable=AsyncMock,
            ) as mock_write,
        ):
            await _write_memory_candidate(
                tenant_id=1,
                user_id=1,
                conversation_id=42,
                user_message="Test bericht",
                assistant_response="Test antwoord",
                db_factory=db_factory,
            )

        mock_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_write_proceeds_when_personalization_consent_granted(self):
        """Memory write proceeds als PERSONALIZATION consent verleend is (SP-CVA-COMP-002)."""
        from src.core.services.cva_service import _write_memory_candidate

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        @MagicMock
        def db_factory():
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _ctx():
                yield mock_session

            return _ctx()

        with (
            patch(
                "src.core.governance.cookie_consent.CookieConsentManager.is_consent_given",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.domains.memory.services.memory_write_service.MemoryWriteService.write",
                new_callable=AsyncMock,
            ) as mock_write,
        ):
            await _write_memory_candidate(
                tenant_id=1,
                user_id=1,
                conversation_id=42,
                user_message="Test",
                assistant_response="Antwoord",
                db_factory=db_factory,
            )

        mock_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_memory_write_exception_absorbed_when_write_service_raises(self):
        """MemoryWriteService.write() fout wordt geabsorbeerd -- nooit gepropageerd (SP-CVA-COMP-002)."""
        from src.core.services.cva_service import _write_memory_candidate

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        @MagicMock
        def db_factory():
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def _ctx():
                yield mock_session

            return _ctx()

        with (
            patch(
                "src.core.governance.cookie_consent.CookieConsentManager.is_consent_given",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "src.domains.memory.services.memory_write_service.MemoryWriteService.write",
                new_callable=AsyncMock,
                side_effect=RuntimeError("memory service unavailable"),
            ),
        ):
            # Must not raise -- _write_memory_candidate is fire-and-forget
            await _write_memory_candidate(
                tenant_id=1,
                user_id=1,
                conversation_id=42,
                user_message="Test",
                assistant_response="Antwoord",
                db_factory=db_factory,
            )
