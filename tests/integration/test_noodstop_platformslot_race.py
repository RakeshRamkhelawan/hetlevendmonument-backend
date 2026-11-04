"""Het platformslot houdt stand als het platform schrijft TUSSEN lezen en schrijven (Gate 2, punt 2).

Een beheerder van de klant heft de noodstop op. Net voordat zijn schrijfstap de database bereikt,
zet het platform de klant stil (een eigen verbinding, echte commit). De schrijfstap van de klant moet
dan WEIGEREN: het platformslot mag niet door een race verdwijnen. De test vervangt niets in de
service; hij laat alleen het platform schrijven op het moment vlak voor de schrijfstap van de klant.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.governance.noodstop_service import NoodstopDoorPlatformGezet, NoodstopService
from src.core.repositories.tenant_noodstop_repository import TenantNoodstopRepository
from tests.fixtures.testdatabase import testdatabase_url

KLANT = 1

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.noodstop_echt]


async def _opruimen() -> None:
    engine = create_async_engine(testdatabase_url())
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM tenant_noodstop WHERE tenant_id = :t"), {"t": KLANT}
            )
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _schoon() -> AsyncGenerator[None, None]:
    await _opruimen()
    yield
    await _opruimen()


async def _gebruiker() -> int:
    """Een echte gebruiker van de klant: de stand en de auditregel verwijzen ernaar (FK)."""
    engine = create_async_engine(testdatabase_url())
    try:
        async with engine.begin() as conn:
            return int(
                (
                    await conn.execute(
                        text(
                            "INSERT INTO users (email, hashed_password, tenant_id, is_active, "
                            "is_superuser) VALUES (:e, 'x', :t, false, false) RETURNING id"
                        ),
                        {"e": f"noodstop-race-{uuid4().hex}@example.test", "t": KLANT},
                    )
                ).scalar_one()
            )
    finally:
        await engine.dispose()


async def _schrijf(stilgezet: bool, *, door_platform: bool, reden: str) -> None:
    engine = create_async_engine(testdatabase_url())
    try:
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as sessie:
            await TenantNoodstopRepository(sessie).set_stand(
                KLANT, stilgezet, reden=reden, user_id=None, door_platform=door_platform
            )
            await sessie.commit()
    finally:
        await engine.dispose()


async def _stand() -> tuple[bool, bool, str | None]:
    engine = create_async_engine(testdatabase_url())
    try:
        async with engine.connect() as conn:
            rij = (
                await conn.execute(
                    text(
                        "SELECT is_stilgezet, changed_by_platform, reden FROM tenant_noodstop "
                        "WHERE tenant_id = :t"
                    ),
                    {"t": KLANT},
                )
            ).one()
            return bool(rij[0]), bool(rij[1]), rij[2]
    finally:
        await engine.dispose()


def _platform_schrijft_vlak_voor_de_schrijfstap(
    monkeypatch: pytest.MonkeyPatch, gebeurd: list[bool]
) -> None:
    """Het platform zet de klant stil op het moment dat de schrijfstap van de klant begint."""
    origineel: Callable[..., Awaitable[Any]] = TenantNoodstopRepository.set_stand

    async def met_race(
        self: TenantNoodstopRepository, tenant_id: int, stilgezet: bool, **kw: Any
    ) -> Any:
        if not kw["door_platform"] and not gebeurd:
            gebeurd.append(True)
            await _schrijf(True, door_platform=True, reden="platform: misbruik")
        return await origineel(self, tenant_id, stilgezet, **kw)

    monkeypatch.setattr(TenantNoodstopRepository, "set_stand", met_race)


async def test_een_platformstop_tussen_lezen_en_schrijven_blijft_staan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gebeurd: list[bool] = []
    _platform_schrijft_vlak_voor_de_schrijfstap(monkeypatch, gebeurd)
    engine = create_async_engine(testdatabase_url())
    try:
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as sessie:
            with pytest.raises(NoodstopDoorPlatformGezet):
                await NoodstopService(sessie).zet_stand(
                    KLANT,
                    False,
                    reden="klant: weer aan",
                    user_id=await _gebruiker(),
                    door_platform=False,
                    source_ip="127.0.0.1",
                    endpoint="/api/v1/noodstop",
                )
    finally:
        await engine.dispose()
    assert gebeurd, "het platform heeft niet geschreven: de test meet niets"
    assert await _stand() == (True, True, "platform: misbruik")


async def test_de_klant_zet_zonder_race_gewoon_stil_en_op(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine(testdatabase_url())
    try:
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as sessie:
            service = NoodstopService(sessie)
            await service.zet_stand(
                KLANT, True, reden="klant: stil", user_id=await _gebruiker(), door_platform=False,
                source_ip="127.0.0.1", endpoint="/api/v1/noodstop",
            )  # fmt: skip
        assert await _stand() == (True, False, "klant: stil")
    finally:
        await engine.dispose()


async def test_het_platform_mag_een_platformstop_wel_opheffen() -> None:
    await _schrijf(True, door_platform=True, reden="platform: misbruik")
    await _schrijf(False, door_platform=True, reden="platform: opgelost")
    assert await _stand() == (False, True, "platform: opgelost")
