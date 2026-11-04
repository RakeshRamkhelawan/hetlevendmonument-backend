"""Noodstop per klant: het platform zet een ANDERE klant stil, onder echte RLS (ADR-036 OP-03).

De gewone integratietests lopen als superuser en zien dus geen RLS. Deze test maakt een rol zonder
superuser- en zonder bypass-rechten en voert de service daarmee uit: de sessie staat op de klant van
de platformbeheerder (klant 2) en schrijft voor klant 1.

Gemeten: zonder `adopt_tenant` weigert de RLS die rij (`new row violates row-level security policy`);
met `door_platform=True` slaagt het en staat de stand er voor klant 1, niet voor klant 2.
"""

from __future__ import annotations

import importlib.util
from collections.abc import AsyncGenerator
from pathlib import Path
from types import ModuleType

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.governance.noodstop_service import NoodstopService
from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id
from tests.fixtures.testdatabase import testdatabase_url

ROL = "rls_noodstop_test"
KLANT_DOEL, KLANT_PLATFORM = 1, 2


def _migratie() -> ModuleType:
    """De migratie zelf, zodat de test dezelfde policy gebruikt als productie (een bron)."""
    pad = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "alembic"
        / "versions"
        / "20261020_tenant_noodstop.py"
    )
    spec = importlib.util.spec_from_file_location("migratie_noodstop", pad)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.noodstop_echt]


@pytest_asyncio.fixture
async def beperkte_engine() -> AsyncGenerator[tuple[AsyncEngine, int], None]:
    """Een engine met een rol zonder superuser; en een echte gebruiker van klant 2."""
    beheer = create_async_engine(testdatabase_url())
    try:
        async with beheer.begin() as conn:
            await conn.execute(text("DELETE FROM tenant_noodstop"))
            if await _rol_bestaat(conn):
                await conn.execute(text(f"DROP OWNED BY {ROL}"))
            await conn.execute(text(f"DROP ROLE IF EXISTS {ROL}"))
            await conn.execute(
                text(f"CREATE ROLE {ROL} LOGIN PASSWORD 'rls' NOSUPERUSER NOBYPASSRLS")
            )
            await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {ROL}"))
            await conn.execute(text(f"GRANT SELECT ON tenants, users TO {ROL}"))
            await conn.execute(text(f"GRANT SELECT, INSERT, UPDATE ON tenant_noodstop TO {ROL}"))
            await conn.execute(text(f"GRANT USAGE ON SEQUENCE tenant_noodstop_id_seq TO {ROL}"))
            await conn.execute(text(f"GRANT SELECT, INSERT ON audit_logs TO {ROL}"))
            await conn.execute(text(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {ROL}"))
            # De integratie-database krijgt zijn RLS-policies uit een vaste lijst; deze tabel staat
            # daar niet in. Dezelfde policy als de migratie, uit de migratie zelf.
            migratie = _migratie()
            await conn.execute(text("ALTER TABLE tenant_noodstop ENABLE ROW LEVEL SECURITY"))
            await conn.execute(text(f"DROP POLICY IF EXISTS {migratie._POLICY} ON tenant_noodstop"))
            await conn.execute(
                text(
                    f"CREATE POLICY {migratie._POLICY} ON tenant_noodstop "
                    f"FOR ALL USING ({migratie._EXPRESSIE})"
                )
            )
            email = "rls-noodstop@integration.test"
            gebruiker = (
                await conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})
            ).scalar_one_or_none()
            if gebruiker is None:
                gebruiker = (
                    await conn.execute(
                        text(
                            "INSERT INTO users (email, hashed_password, tenant_id, is_active, "
                            "is_superuser) VALUES (:e, 'x', :t, true, true) RETURNING id"
                        ),
                        {"e": email, "t": KLANT_PLATFORM},
                    )
                ).scalar_one()
        url = make_url(testdatabase_url()).set(username=ROL, password="rls")
        engine = create_async_engine(url)
        try:
            yield engine, int(gebruiker)
        finally:
            await engine.dispose()
    finally:
        async with beheer.begin() as conn:
            await conn.execute(text("DELETE FROM tenant_noodstop"))
            await conn.execute(text(f"DROP OWNED BY {ROL}"))
            await conn.execute(text(f"DROP ROLE IF EXISTS {ROL}"))
            migratie = _migratie()
            await conn.execute(text(f"DROP POLICY IF EXISTS {migratie._POLICY} ON tenant_noodstop"))
            await conn.execute(text("ALTER TABLE tenant_noodstop DISABLE ROW LEVEL SECURITY"))
        await beheer.dispose()


async def _rol_bestaat(conn: object) -> bool:
    uit = await conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROL})  # type: ignore[attr-defined]
    return uit.first() is not None


async def _zet(engine: AsyncEngine, user_id: int, *, door_platform: bool) -> None:
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    set_tenant_id(KLANT_PLATFORM)
    try:
        async with maker() as sessie:
            await sessie.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(KLANT_PLATFORM)},
            )
            await NoodstopService(sessie).zet_stand(
                KLANT_DOEL,
                True,
                reden="platform test",
                user_id=user_id,
                door_platform=door_platform,
                source_ip="127.0.0.1",
                endpoint="/test",
            )
    finally:
        clear_tenant_context()


async def _staat_stil(klant: int) -> bool | None:
    beheer = create_async_engine(testdatabase_url())
    try:
        async with beheer.connect() as conn:
            uit = await conn.execute(
                text("SELECT is_stilgezet FROM tenant_noodstop WHERE tenant_id = :t"), {"t": klant}
            )
            rij = uit.scalar_one_or_none()
            return None if rij is None else bool(rij)
    finally:
        await beheer.dispose()


async def _aantal_auditregels(klant: int) -> int:
    beheer = create_async_engine(testdatabase_url())
    try:
        async with beheer.connect() as conn:
            uit = await conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE tenant_id = :t AND event_type = :e"),
                {"t": klant, "e": "noodstop_changed"},
            )
            return int(uit.scalar_one())
    finally:
        await beheer.dispose()


async def test_zonder_adopt_tenant_weigert_de_rls_een_rij_voor_een_andere_klant(
    beperkte_engine: tuple[AsyncEngine, int],
) -> None:
    engine, user_id = beperkte_engine
    with pytest.raises(DBAPIError):
        await _zet(engine, user_id, door_platform=False)
    assert await _staat_stil(KLANT_DOEL) is None


async def test_het_platform_zet_een_andere_klant_stil_onder_rls(
    beperkte_engine: tuple[AsyncEngine, int],
) -> None:
    engine, user_id = beperkte_engine
    await _zet(engine, user_id, door_platform=True)
    assert await _staat_stil(KLANT_DOEL) is True
    assert await _staat_stil(KLANT_PLATFORM) is None
    assert await _aantal_auditregels(KLANT_DOEL) == 1
