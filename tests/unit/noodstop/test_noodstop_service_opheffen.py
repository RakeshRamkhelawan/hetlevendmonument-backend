"""Opheffen van de noodstop legt de auditregel vast in DEZELFDE transactie, fail-closed (Gate 2, punt 5).

Een stop die wordt opgeheven zonder spoor is erger dan een stop die blijft staan: opheffen zet
agents weer aan. Lukt de auditregel niet, dan wordt de stop NIET opgeheven (rollback) en weet de
beheerder dat. Zetten mag best-effort blijven: een kapot logboek mag een klant in nood niet
onbeschermd laten.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.governance import noodstop_service as ns
from src.core.repositories.tenant_noodstop_repository import NoodstopStand

KLANT = 5


def _stand(stilgezet: bool, platform: bool = False) -> NoodstopStand:
    return NoodstopStand(
        tenant_id=KLANT,
        is_stilgezet=stilgezet,
        reden="r",
        changed_by_user_id=1,
        changed_by_platform=platform,
        changed_at=datetime.now(timezone.utc),
    )


def _service(
    monkeypatch: pytest.MonkeyPatch, log_event: Any
) -> tuple[ns.NoodstopService, MagicMock, list[str]]:
    volgorde: list[str] = []
    db = MagicMock()

    async def commit() -> None:
        volgorde.append("commit")

    async def rollback() -> None:
        volgorde.append("rollback")

    db.commit = AsyncMock(side_effect=commit)
    db.rollback = AsyncMock(side_effect=rollback)
    service = ns.NoodstopService(db)

    async def set_stand(tenant_id: int, stilgezet: bool, **kw: Any) -> NoodstopStand:
        volgorde.append("set_stand")
        return _stand(stilgezet)

    async def get(tenant_id: int) -> NoodstopStand:
        return _stand(True)

    service._repo = MagicMock(set_stand=set_stand, get=get)  # type: ignore[assignment]

    async def audit(**kw: Any) -> bool:
        volgorde.append("audit")
        return await log_event(**kw)

    monkeypatch.setattr(ns.AuditService, "log_event", audit)
    return service, db, volgorde


async def _zet(service: ns.NoodstopService, stilgezet: bool) -> NoodstopStand:
    return await service.zet_stand(
        KLANT,
        stilgezet,
        reden="reden",
        user_id=1,
        door_platform=False,
        source_ip="127.0.0.1",
        endpoint="/api/v1/noodstop",
    )


@pytest.mark.asyncio
async def test_opheffen_schrijft_de_auditregel_voor_de_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, volgorde = _service(monkeypatch, AsyncMock(return_value=True))
    await _zet(service, False)
    assert volgorde == ["set_stand", "audit", "commit"]


@pytest.mark.asyncio
async def test_opheffen_zonder_auditregel_wordt_teruggedraaid_en_gemeld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, volgorde = _service(monkeypatch, AsyncMock(return_value=False))
    with pytest.raises(ns.NoodstopAuditMislukt):
        await _zet(service, False)
    assert "commit" not in volgorde
    assert volgorde[-1] == "rollback"


@pytest.mark.asyncio
async def test_opheffen_met_een_auditfout_wordt_teruggedraaid_en_gemeld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, volgorde = _service(monkeypatch, AsyncMock(side_effect=RuntimeError("stuk")))
    with pytest.raises(ns.NoodstopAuditMislukt):
        await _zet(service, False)
    assert "commit" not in volgorde
    assert volgorde[-1] == "rollback"


@pytest.mark.asyncio
async def test_zetten_blijft_best_effort_en_de_stop_staat_dan_toch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, volgorde = _service(monkeypatch, AsyncMock(side_effect=RuntimeError("stuk")))
    stand = await _zet(service, True)
    assert stand.is_stilgezet
    assert volgorde[:2] == ["set_stand", "commit"]


@pytest.mark.asyncio
async def test_de_route_meldt_een_niet_vastgelegde_opheffing_als_503() -> None:
    from fastapi import HTTPException

    from src.core.api.v1.noodstop.router import _zet as route_zet
    from src.core.api.v1.noodstop.schemas import NoodstopRequest

    service = MagicMock()
    service.zet_stand = AsyncMock(side_effect=ns.NoodstopAuditMislukt())
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.url.path = "/api/v1/noodstop"
    with pytest.raises(HTTPException) as fout:
        await route_zet(
            service,
            request,
            KLANT,
            NoodstopRequest(is_stilgezet=False, reden="weer aan"),
            MagicMock(id=1),
            door_platform=False,
        )
    assert fout.value.status_code == 503
    assert fout.value.detail["code"] == "NOODSTOP_NIET_OPGEHEVEN"  # type: ignore[index]
