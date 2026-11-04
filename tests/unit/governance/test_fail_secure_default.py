"""RC-SUP-2: governance-gate default MUST be fail-secure.

Historisch stond CVA_GOVERNANCE_FAIL_SECURE default op "false" (fail-OPEN): bij
een Council-infrastructuurfout ging de chat gewoon door zonder goedkeuring. Die
aanname is zelf onveilig. Deze tests borgen dat de default fail-SECURE is (bij
Council-fout: request geblokkeerd, niet doorlopen naar de LLM).

Kern-rode test: 3.1 (default is fail-secure).
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException

import src.core.services.cva_service as cva_mod


def _reload_with_unset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reload cva_service met de env-var verwijderd zodat de default geldt."""
    monkeypatch.delenv("CVA_GOVERNANCE_FAIL_SECURE", raising=False)
    importlib.reload(cva_mod)


class TestFailSecureDefault:
    def test_default_is_fail_secure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """3.1 -- met CVA_GOVERNANCE_FAIL_SECURE ongezet is de default fail-SECURE (ROOD voor fix)."""
        _reload_with_unset_env(monkeypatch)
        try:
            assert cva_mod._CVA_FAIL_SECURE is True, (
                "CVA_GOVERNANCE_FAIL_SECURE default moet fail-secure (True) zijn (RC-SUP-2)."
            )
        finally:
            # Laat de module in de veilige default achter voor volgende tests.
            importlib.reload(cva_mod)

    @pytest.mark.asyncio
    async def test_council_infra_error_blocks_chat_when_fail_secure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """3.1b -- fail-secure: Council-infrastructuurfout blokkeert chat (503), LLM niet aangeroepen."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Force the flag explicitly (setattr, not reload) to test behaviour in isolation.
        monkeypatch.setattr(cva_mod, "_CVA_FAIL_SECURE", True)

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        mock_llm = MagicMock()
        mock_llm.provider.provider_name = "gemini"
        mock_llm.generate = AsyncMock(return_value=("Antwoord", {"total_tokens": 1}))

        with patch.object(
            cva_mod,
            "build_council",
            new_callable=AsyncMock,
            side_effect=RuntimeError("council backend unreachable"),
        ):
            svc = cva_mod.CVAService(db_session=mock_db, llm_service=mock_llm)
            with pytest.raises(HTTPException) as exc_info:
                await svc.chat(message="Hallo", user_id=1, tenant_id=1)

        assert exc_info.value.status_code == 503
        mock_llm.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_council_infra_error_blocks_chat_stream_when_fail_secure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """3.1c -- fail-secure geldt symmetrisch voor chat_stream (503 voor de eerste yield)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        monkeypatch.setattr(cva_mod, "_CVA_FAIL_SECURE", True)

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        mock_llm = MagicMock()
        mock_llm.stream_generate = AsyncMock()

        with patch.object(
            cva_mod,
            "build_council",
            new_callable=AsyncMock,
            side_effect=RuntimeError("council backend unreachable"),
        ):
            svc = cva_mod.CVAService(db_session=mock_db, llm_service=mock_llm)
            with pytest.raises(HTTPException) as exc_info:
                async for _ in svc.chat_stream(message="Hallo", user_id=1, tenant_id=1):
                    pass

        assert exc_info.value.status_code == 503
        mock_llm.stream_generate.assert_not_called()
