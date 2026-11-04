"""Noodstop per klant, de API: wie mag stilzetten, en wat wordt vastgelegd (ADR-036 OP-03).

Echte app-stack en echte Postgres, de echte rolcontrole en de echte service. Klant 1 en klant 2.

Gemeten: een beheerder zet de EIGEN klant stil en op; een medewerker niet; een beheerder van klant 2
kan klant 1 niet stilzetten (de klant komt uit de JWT, een `tenant_id` in de body wordt geweigerd, de
platformroute vraagt een platformbeheerder); een stop van het platform kan de klant niet opheffen;
elke wijziging geeft een auditregel met wie, waarom en de nieuwe stand.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.services.rbac_service import RBACService
from tests.integration.test_packs_execute_route import (  # noqa: F401
    _client,
    beheerder,
    medewerker,
    standaardrollen,
)

URL = "/api/v1/noodstop"
KLANT_A, KLANT_B = 1, 2
EVENT = "noodstop_changed"
EMAIL_B = "noodstop-b@integration.test"
EMAIL_P = "noodstop-p@integration.test"


def _platform_url(tenant_id: int) -> str:
    return f"/api/v1/platform/klanten/{tenant_id}/noodstop"


async def _client_van(
    app: Any,
    sessie: AsyncSession,
    *,
    tenant: int,
    rollen: list[str],
    superuser: bool,
    uid: int,
    email: str,
) -> AsyncGenerator[AsyncClient, None]:
    from tests.integration.conftest import _build_test_token

    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.auth.auth_service import UserResponse
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db

    async def _db() -> AsyncGenerator[AsyncSession, None]:
        yield sessie

    async def _geen_csrf() -> None:
        return None

    gebruiker = UserResponse(
        id=uid, email=email, tenant_id=tenant, roles=rollen, is_superuser=superuser
    )
    overrides: dict[Any, Any] = {
        get_db: _db,
        api_get_db: _db,
        get_current_user: lambda: gebruiker,
        validate_csrf_token: _geen_csrf,
    }
    app.dependency_overrides.update(overrides)
    token = _build_test_token(user_id=uid, email=email, tenant_id=tenant)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


async def _maak_gebruiker(sessie: AsyncSession, tenant: int, email: str, superuser: bool) -> int:
    """Een echte gebruiker: de accountcontrole van de app leest hem uit de database."""
    return int(
        (
            await sessie.execute(
                text(
                    "INSERT INTO users (email, hashed_password, tenant_id, is_active, is_superuser) "
                    "VALUES (:e, 'x', :t, true, :s) RETURNING id"
                ),
                {"e": email, "t": tenant, "s": superuser},
            )
        ).scalar_one()
    )


@pytest_asyncio.fixture
async def beheerder_klant_b(
    integration_app: Any, standaardrollen: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    await RBACService(standaardrollen).ensure_default_roles(KLANT_B)
    uid = await _maak_gebruiker(standaardrollen, KLANT_B, EMAIL_B, False)
    rol_id = (
        await standaardrollen.execute(
            text("SELECT id FROM roles WHERE name = 'admin' AND tenant_id = :t"), {"t": KLANT_B}
        )
    ).scalar_one()
    await standaardrollen.execute(
        text("INSERT INTO user_roles (user_id, role_id, tenant_id) VALUES (:u, :r, :t)"),
        {"u": uid, "r": rol_id, "t": KLANT_B},
    )
    await standaardrollen.commit()
    async for c in _client_van(
        integration_app,
        standaardrollen,
        tenant=KLANT_B,
        rollen=["admin"],
        superuser=False,
        uid=uid,
        email=EMAIL_B,
    ):
        yield c


@pytest_asyncio.fixture
async def platformbeheerder(
    integration_app: Any, standaardrollen: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    uid = await _maak_gebruiker(standaardrollen, KLANT_B, EMAIL_P, True)
    await standaardrollen.commit()
    async for c in _client_van(
        integration_app,
        standaardrollen,
        tenant=KLANT_B,
        rollen=["admin"],
        superuser=True,
        uid=uid,
        email=EMAIL_P,
    ):
        yield c


async def _stand(sessie: AsyncSession, tenant_id: int) -> bool | None:
    rij = (
        await sessie.execute(
            text("SELECT is_stilgezet FROM tenant_noodstop WHERE tenant_id = :t"),
            {"t": tenant_id},
        )
    ).scalar_one_or_none()
    return None if rij is None else bool(rij)


async def _auditregels(sessie: AsyncSession, tenant_id: int) -> list[dict[str, Any]]:
    rijen = (
        await sessie.execute(
            text(
                "SELECT user_id, event_metadata FROM audit_logs "
                "WHERE tenant_id = :t AND event_type = :e ORDER BY id"
            ),
            {"t": tenant_id, "e": EVENT},
        )
    ).all()
    return [{"user_id": r[0], "metadata": r[1]} for r in rijen]


@pytest.mark.integration
@pytest.mark.asyncio
class TestWieMagStilzetten:
    async def test_een_beheerder_zet_de_eigen_klant_stil_en_heft_op(
        self, beheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        aan = await beheerder.put(
            URL, json={"is_stilgezet": True, "reden": "Vermoeden van misbruik"}
        )
        assert aan.status_code == 200, aan.text
        assert aan.json()["data"]["is_stilgezet"] is True
        assert await _stand(standaardrollen, KLANT_A) is True
        uit = await beheerder.put(URL, json={"is_stilgezet": False, "reden": "Onderzocht, in orde"})
        assert uit.status_code == 200, uit.text
        assert await _stand(standaardrollen, KLANT_A) is False

    async def test_een_medewerker_mag_de_noodstop_niet_bedienen(
        self, medewerker: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        antwoord = await medewerker.put(URL, json={"is_stilgezet": True, "reden": "test"})
        assert antwoord.status_code == 403, antwoord.text
        assert await _stand(standaardrollen, KLANT_A) is None

    async def test_een_beheerder_van_klant_b_kan_klant_a_niet_stilzetten(
        self, beheerder_klant_b: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        # Via de eigen route raakt hij alleen klant B: de klant komt uit de JWT.
        eigen = await beheerder_klant_b.put(URL, json={"is_stilgezet": True, "reden": "eigen"})
        assert eigen.status_code == 200, eigen.text
        assert await _stand(standaardrollen, KLANT_A) is None
        assert await _stand(standaardrollen, KLANT_B) is True
        # Een tenant_id in de body wordt geweigerd, niet genegeerd.
        body = await beheerder_klant_b.put(
            URL, json={"is_stilgezet": True, "reden": "x", "tenant_id": KLANT_A}
        )
        assert body.status_code == 422, body.text
        # De platformroute voor een andere klant is voor een gewone beheerder dicht.
        platform = await beheerder_klant_b.put(
            _platform_url(KLANT_A), json={"is_stilgezet": True, "reden": "x"}
        )
        assert platform.status_code == 403, platform.text
        assert await _stand(standaardrollen, KLANT_A) is None

    async def test_een_beheerder_van_klant_b_leest_de_stand_van_klant_a_niet(
        self, beheerder_klant_b: AsyncClient
    ) -> None:
        antwoord = await beheerder_klant_b.get(_platform_url(KLANT_A))
        assert antwoord.status_code == 403, antwoord.text

    async def test_een_reden_is_verplicht(self, beheerder: AsyncClient) -> None:
        for body in ({"is_stilgezet": True}, {"is_stilgezet": True, "reden": ""}):
            antwoord = await beheerder.put(URL, json=body)
            assert antwoord.status_code == 422, antwoord.text


@pytest.mark.integration
@pytest.mark.asyncio
class TestPlatformSlot:
    async def test_het_platform_zet_een_andere_klant_stil(
        self, platformbeheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        antwoord = await platformbeheerder.put(
            _platform_url(KLANT_A), json={"is_stilgezet": True, "reden": "Besluit platform"}
        )
        assert antwoord.status_code == 200, antwoord.text
        assert antwoord.json()["data"]["door_platform"] is True
        assert await _stand(standaardrollen, KLANT_A) is True

    async def test_de_klant_heft_een_stop_van_het_platform_niet_zelf_op(
        self,
        platformbeheerder: AsyncClient,
        beheerder: AsyncClient,
        standaardrollen: AsyncSession,
    ) -> None:
        await platformbeheerder.put(
            _platform_url(KLANT_A), json={"is_stilgezet": True, "reden": "Besluit platform"}
        )
        poging = await beheerder.put(URL, json={"is_stilgezet": False, "reden": "toch niet"})
        assert poging.status_code == 403, poging.text
        assert poging.json()["detail"]["code"] == "NOODSTOP_DOOR_PLATFORM"
        assert await _stand(standaardrollen, KLANT_A) is True


@pytest.mark.integration
@pytest.mark.asyncio
class TestLogboek:
    async def test_aanzetten_en_opheffen_staan_in_het_logboek_met_wie_en_waarom(
        self, beheerder: AsyncClient, standaardrollen: AsyncSession
    ) -> None:
        await beheerder.put(URL, json={"is_stilgezet": True, "reden": "Reden een"})
        await beheerder.put(URL, json={"is_stilgezet": False, "reden": "Reden twee"})
        regels = await _auditregels(standaardrollen, KLANT_A)
        assert len(regels) == 2
        assert [r["metadata"]["is_stilgezet"] for r in regels] == [True, False]
        assert [r["metadata"]["reden"] for r in regels] == ["Reden een", "Reden twee"]
        assert all(r["user_id"] == 1 for r in regels)
