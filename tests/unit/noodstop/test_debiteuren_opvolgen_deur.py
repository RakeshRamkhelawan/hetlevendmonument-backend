"""`volg_debiteuren_op` is een deur: een stilgezette klant escaleert geen dossiers (Gate 2, punt 1).

Escaleren zet een dossier op `geescaleerd` en dat is het wettelijke vervolg van een herinnering: een
stilgezette klant mag dat niet krijgen. Het dossier blijft `herinnerd` en komt na het opheffen van
de stop alsnog aan de beurt. Een onleesbare stand telt als stil (fail-closed).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
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


@asynccontextmanager
async def _fabriek():  # type: ignore[no-untyped-def]
    yield MagicMock()


async def _draai(monkeypatch: pytest.MonkeyPatch, kandidaten: list[tuple[int, int]]) -> list[int]:
    from src.core.tasks import debiteuren_tasks as dt

    geescaleerd: list[int] = []

    async def lijst(sessie: object, nu: object) -> list[tuple[int, int, object, int]]:
        # Sinds BE-DEB-004 (develop) geeft de lijst ook de eigen grens en termijn van de tenant mee.
        return [(rid, tid, "grens", 14) for rid, tid in kandidaten]

    async def escaleer(sessie: object, receivable_id: int, tenant_id: int, grens: object) -> bool:
        geescaleerd.append(tenant_id)
        return True

    monkeypatch.setattr(dt, "_escalatiekandidaten", lijst)
    monkeypatch.setattr(dt, "_escaleer", escaleer)
    monkeypatch.setattr(dt, "_log_escalatie", AsyncMock())
    monkeypatch.setattr(dt, "_meld_escalatie", AsyncMock())
    await dt.volg_debiteuren_op_async(sessie_fabriek=_fabriek)
    return geescaleerd


@pytest.mark.asyncio
async def test_een_dossier_van_de_stilgezette_klant_blijft_herinnerd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await _draai(monkeypatch, [(10, STIL), (20, ACTIEF)]) == [ACTIEF]


@pytest.mark.asyncio
async def test_een_onleesbare_stand_escaleert_niet(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await _draai(monkeypatch, [(10, STORING)]) == []
