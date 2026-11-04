"""De deuren van de HITL-goedkeuring en van de klantenservice-actor (CVA).

Klant 1 staat stil, klant 2 is actief. De lezer van de stand is de enige echte vervanging (de grens);
de dingen NA de deur zijn vervangen en doen mee als bewijs dat de deur doorliet of niet.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.core.noodstop import guard
from src.core.noodstop.guard import MELDING_STIL

STIL, ACTIEF = 1, 2


@pytest.fixture(autouse=True)
def _klant_1_staat_stil(monkeypatch: pytest.MonkeyPatch) -> None:
    async def lezer(tenant_id: int) -> bool:
        return tenant_id == STIL

    monkeypatch.setattr(guard, "_lees_stand", lezer)


async def _keur_goed(monkeypatch: pytest.MonkeyPatch, tenant_id: int) -> MagicMock:
    from src.core.api.v1.tool_broker import hitl_router

    repository = MagicMock()
    repository.return_value.get = AsyncMock(side_effect=RuntimeError("DOORGELATEN"))
    monkeypatch.setattr(hitl_router, "HITLTicketRepository", repository)
    monkeypatch.setattr(hitl_router, "_require_approver", AsyncMock())
    ruwe_functie = hitl_router.approve_hitl_request.__wrapped__  # type: ignore[attr-defined]
    await ruwe_functie(
        request=SimpleNamespace(ticket_ref="t-1"),
        http_request=MagicMock(),
        current_user=SimpleNamespace(tenant_id=tenant_id, id=9),
        db=MagicMock(),
        broker=MagicMock(),
        _csrf=None,
    )
    return repository


@pytest.mark.asyncio
async def test_een_goedkeuring_van_de_stilgezette_klant_wordt_geweigerd_voor_het_ticket_wordt_aangeraakt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.api.v1.tool_broker import hitl_router

    repository = MagicMock()
    monkeypatch.setattr(hitl_router, "HITLTicketRepository", repository)
    with pytest.raises(HTTPException) as fout:
        await _keur_goed(monkeypatch, STIL)
    assert fout.value.status_code == 403
    assert fout.value.detail == MELDING_STIL


@pytest.mark.asyncio
async def test_een_goedkeuring_van_een_andere_klant_komt_voorbij_de_deur(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="DOORGELATEN"):
        await _keur_goed(monkeypatch, ACTIEF)


async def _cva(monkeypatch: pytest.MonkeyPatch, tenant_id: int) -> AsyncMock:
    from src.core.tasks import cva_tasks

    initialiseer = AsyncMock()
    monkeypatch.setattr(cva_tasks.db_manager, "initialize", initialiseer)

    def fabriek() -> object:
        raise RuntimeError("DOORGELATEN")

    await cva_tasks._process_cva_message_async(
        {"tenant_id": tenant_id, "channel": "telegram", "text": "hallo", "sender_id": "5"},
        fabriek,  # type: ignore[arg-type]
    )
    return initialiseer


@pytest.mark.asyncio
async def test_de_klantenservice_antwoordt_de_stilgezette_klant_niet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.tasks import cva_tasks

    initialiseer = AsyncMock()
    monkeypatch.setattr(cva_tasks.db_manager, "initialize", initialiseer)
    await cva_tasks._process_cva_message_async(
        {"tenant_id": STIL, "channel": "telegram", "text": "hallo", "sender_id": "5"},
        lambda: (_ for _ in ()).throw(RuntimeError("DOORGELATEN")),  # type: ignore[arg-type,return-value]
    )
    initialiseer.assert_not_awaited()


@pytest.mark.asyncio
async def test_de_klantenservice_gaat_door_voor_een_andere_klant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="DOORGELATEN"):
        await _cva(monkeypatch, ACTIEF)
