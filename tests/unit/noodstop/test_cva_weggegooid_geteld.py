"""Een CVA-bericht voor een stilgezette klant wordt weggegooid, maar GETELD en gelogd (besluit C).

Zo is na het opheffen van de stop zichtbaar hoeveel berichten onbeantwoord bleven: een teller (per
kanaal) en een auditregel per bericht, zonder de tekst of de afzender (persoonsgegevens).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.noodstop import guard

STIL, ACTIEF, STORING = 1, 2, 3


@pytest.fixture(autouse=True)
def _standen(monkeypatch: pytest.MonkeyPatch) -> None:
    async def lezer(tenant_id: int) -> bool:
        if tenant_id == STORING:
            raise ConnectionError("db weg")
        return tenant_id == STIL

    monkeypatch.setattr(guard, "_lees_stand", lezer)


def _waarde(kanaal: str) -> float:
    from src.core.noodstop.metrics import CVA_BERICHTEN_WEGGEGOOID

    return CVA_BERICHTEN_WEGGEGOOID.labels(channel=kanaal)._value.get()


def _verzoek(tenant_id: int) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "channel": "telegram",
        "text": "geheim bericht",
        "sender_id": "12345",
    }


@pytest.fixture
def audit(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    from src.core.noodstop import weggegooid

    logger = AsyncMock()
    monkeypatch.setattr(weggegooid.AuditService, "log_action", logger)

    @asynccontextmanager
    async def adopt(sessie: object, tenant_id: int):  # type: ignore[no-untyped-def]
        yield

    monkeypatch.setattr(weggegooid, "adopt_tenant", adopt)
    return logger


@asynccontextmanager
async def _fabriek():  # type: ignore[no-untyped-def]
    yield AsyncMock()


@pytest.mark.asyncio
async def test_een_weggegooid_bericht_wordt_geteld_en_gelogd(audit: AsyncMock) -> None:
    from src.core.tasks.cva_tasks import _process_cva_message_async

    voor = _waarde("telegram")
    await _process_cva_message_async(_verzoek(STIL), _fabriek)
    assert _waarde("telegram") == voor + 1
    audit.assert_awaited_once()
    kwargs = audit.await_args.kwargs
    assert kwargs["tenant_id"] == STIL
    assert kwargs["action"] == "noodstop_cva_bericht_weggegooid"
    ruw = repr(kwargs)
    assert "geheim bericht" not in ruw and "12345" not in ruw


@pytest.mark.asyncio
async def test_een_actieve_klant_telt_en_logt_niets(
    audit: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.core.tasks import cva_tasks

    monkeypatch.setattr(
        cva_tasks.db_manager, "initialize", AsyncMock(side_effect=RuntimeError("DOOR"))
    )
    voor = _waarde("telegram")
    with pytest.raises(RuntimeError, match="DOOR"):
        await cva_tasks._process_cva_message_async(_verzoek(ACTIEF), _fabriek)
    assert _waarde("telegram") == voor
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_een_onbekende_stand_is_geen_weggooien(audit: AsyncMock) -> None:
    from src.core.noodstop.guard import KlantStilgezet
    from src.core.tasks.cva_tasks import _process_cva_message_async

    voor = _waarde("telegram")
    with pytest.raises(KlantStilgezet):
        await _process_cva_message_async(_verzoek(STORING), _fabriek)
    assert _waarde("telegram") == voor
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_een_kapot_auditlog_houdt_het_weggooien_niet_tegen(
    audit: AsyncMock,
) -> None:
    from src.core.tasks.cva_tasks import _process_cva_message_async

    audit.side_effect = RuntimeError("auditlog stuk")
    voor = _waarde("telegram")
    await _process_cva_message_async(_verzoek(STIL), _fabriek)
    assert _waarde("telegram") == voor + 1
