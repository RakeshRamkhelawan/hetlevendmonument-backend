"""Routes met een tenant-id in pad of querystring: een tenantbeheerder komt niet in een andere tenant.

Getoetst over de ECHTE routes (`register_all_routers`, dus wat `src.main:app` serveert) met
echte JWT's. Opstelling: tenant 2 is de aanvaller (rol `admin`, `*`/`*`, GEEN superuser); tenant 1
is het slachtoffer (een gebruiker met een rol en de tenant zelf); een platformsuperuser
(`is_superuser`) hoort bij tenant 1.

Gemeten bereikbaarheid (zie het rapport): `api/v1/user_management/crud_router.py` en
`api/v1/tenant_management/crud_router.py` worden door `register_all_routers` NIET gemount; op
dezelfde paden (`/api/v1/users/...`, `/api/v1/tenants/...`) antwoorden `api/v1/users/` en
`api/v1/tenants/`. Daarom toetst dit bestand die twee.

Groene helften: de beheerder mag zijn EIGEN tenant en zijn eigen gebruikers; de platformsuperuser
mag de tenantgrens over (docstring `can_manage_users` en `is_platform_superuser`).

Mutatiebewijs: zie het rapport; per route is de controle op een kopie weggehaald.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.jwt_handler import jwt_handler
from src.core.database.tenant_query_filter import TenantFilterBypass

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.security]

_AANVALLER_TENANT = 2
_SLACHTOFFER_TENANT = 1


def _kop(user_id: int, email: str, tenant_id: int) -> dict[str, str]:
    token = jwt_handler.create_access_token(
        data={"sub": str(user_id), "user_id": user_id, "email": email, "tenant_id": tenant_id}
    )
    return {"Authorization": f"Bearer {token}"}


async def _maak_gebruiker(
    s: AsyncSession, email: str, tenant_id: int, superuser: bool, rol: str | None
) -> int:
    uid = (
        await s.execute(
            text(
                "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
                "VALUES (:e, 'x', true, :su, :t) RETURNING id"
            ),
            {"e": email, "su": superuser, "t": tenant_id},
        )
    ).scalar_one()
    if rol is not None:
        rol_id = (
            await s.execute(
                text(
                    "INSERT INTO roles (name, tenant_id, is_active) VALUES (:n, :t, true) "
                    "RETURNING id"
                ),
                {"n": rol, "t": tenant_id},
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO role_permissions (role_id, tenant_id, resource, action) "
                "VALUES (:r, :t, '*', '*')"
            ),
            {"r": rol_id, "t": tenant_id},
        )
        await s.execute(
            text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)"),
            {"u": uid, "r": rol_id},
        )
    return int(uid)


@pytest_asyncio.fixture
async def opstelling(postgres_session: AsyncSession) -> AsyncIterator[dict[str, object]]:
    s = postgres_session
    with TenantFilterBypass():
        aanvaller = await _maak_gebruiker(
            s, "aanvaller@grens.test", _AANVALLER_TENANT, False, "admin"
        )
        slachtoffer = await _maak_gebruiker(
            s, "slachtoffer@grens.test", _SLACHTOFFER_TENANT, False, "klantrol"
        )
        platform = await _maak_gebruiker(s, "platform@grens.test", _SLACHTOFFER_TENANT, True, None)
        # De route maakt nieuwe gebruikers aan met de rol `user` van de DOELtenant; zonder die rol
        # weigert hij terecht (fail-secure), en dat zou de groene helft om de verkeerde reden laten falen.
        await s.execute(
            text("INSERT INTO roles (name, tenant_id, is_active) VALUES ('user', :t, true)"),
            {"t": _AANVALLER_TENANT},
        )
        await s.flush()
        naam_slachtoffer = (
            await s.execute(
                text("SELECT name FROM tenants WHERE id = :t"), {"t": _SLACHTOFFER_TENANT}
            )
        ).scalar_one()
    yield {
        "aanvaller": _kop(aanvaller, "aanvaller@grens.test", _AANVALLER_TENANT),
        "platform": _kop(platform, "platform@grens.test", _SLACHTOFFER_TENANT),
        "slachtoffer_id": slachtoffer,
        "naam_slachtoffer": naam_slachtoffer,
    }


def _kopje(o: dict[str, object], sleutel: str) -> dict[str, str]:
    kop = o[sleutel]
    assert isinstance(kop, dict)
    return kop


def _nieuwe_gebruiker(email: str) -> dict[str, object]:
    return {"email": email, "password": "Wachtwoord-123!", "role_ids": []}


# ---------------------------------------------------------------- gebruiker aanmaken (3a)


async def test_a_tenant_admin_cannot_create_a_user_in_another_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    antwoord = await unauthenticated_client.post(
        f"/api/v1/users/?target_tenant_id={_SLACHTOFFER_TENANT}",
        json=_nieuwe_gebruiker("indringer@example.com"),
        headers=_kopje(opstelling, "aanvaller"),
    )
    assert antwoord.status_code == 403, (antwoord.status_code, antwoord.text)


async def test_a_refused_foreign_user_is_not_stored(
    unauthenticated_client: AsyncClient,
    opstelling: dict[str, object],
    postgres_session: AsyncSession,
) -> None:
    await unauthenticated_client.post(
        f"/api/v1/users/?target_tenant_id={_SLACHTOFFER_TENANT}",
        json=_nieuwe_gebruiker("indringer@example.com"),
        headers=_kopje(opstelling, "aanvaller"),
    )
    with TenantFilterBypass():
        aantal = (
            await postgres_session.execute(
                text("SELECT count(*) FROM users WHERE email = 'indringer@example.com'")
            )
        ).scalar_one()
    assert aantal == 0


async def test_a_tenant_admin_can_create_a_user_in_the_own_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    antwoord = await unauthenticated_client.post(
        f"/api/v1/users/?target_tenant_id={_AANVALLER_TENANT}",
        json=_nieuwe_gebruiker("collega@example.com"),
        headers=_kopje(opstelling, "aanvaller"),
    )
    assert (antwoord.status_code, antwoord.json().get("tenant_id")) == (
        201,
        _AANVALLER_TENANT,
    ), antwoord.text


async def test_a_platform_superuser_can_create_a_user_in_another_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    antwoord = await unauthenticated_client.post(
        f"/api/v1/users/?target_tenant_id={_AANVALLER_TENANT}",
        json=_nieuwe_gebruiker("door-platform@example.com"),
        headers=_kopje(opstelling, "platform"),
    )
    assert (antwoord.status_code, antwoord.json().get("tenant_id")) == (
        201,
        _AANVALLER_TENANT,
    ), antwoord.text


async def test_a_tenant_admin_cannot_read_a_user_of_another_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    antwoord = await unauthenticated_client.get(
        f"/api/v1/users/{opstelling['slachtoffer_id']}", headers=_kopje(opstelling, "aanvaller")
    )
    assert antwoord.status_code == 403, (antwoord.status_code, antwoord.text)


async def test_a_tenant_admin_cannot_delete_a_user_of_another_tenant(
    unauthenticated_client: AsyncClient,
    opstelling: dict[str, object],
    postgres_session: AsyncSession,
) -> None:
    await unauthenticated_client.delete(
        f"/api/v1/users/{opstelling['slachtoffer_id']}", headers=_kopje(opstelling, "aanvaller")
    )
    with TenantFilterBypass():
        aantal = (
            await postgres_session.execute(
                text("SELECT count(*) FROM users WHERE id = :i"),
                {"i": opstelling["slachtoffer_id"]},
            )
        ).scalar_one()
    assert aantal == 1


# ---------------------------------------------------------------- tenants (3c)


async def test_a_tenant_admin_cannot_read_another_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    antwoord = await unauthenticated_client.get(
        f"/api/v1/tenants/{_SLACHTOFFER_TENANT}", headers=_kopje(opstelling, "aanvaller")
    )
    assert antwoord.status_code == 403, (antwoord.status_code, antwoord.text)


async def test_a_tenant_admin_cannot_read_the_stats_of_another_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    antwoord = await unauthenticated_client.get(
        f"/api/v1/tenants/{_SLACHTOFFER_TENANT}/stats", headers=_kopje(opstelling, "aanvaller")
    )
    assert antwoord.status_code == 403, (antwoord.status_code, antwoord.text)


async def test_a_tenant_admin_cannot_update_another_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    antwoord = await unauthenticated_client.put(
        f"/api/v1/tenants/{_SLACHTOFFER_TENANT}",
        json={"name": "Overgenomen door tenant 2"},
        headers=_kopje(opstelling, "aanvaller"),
    )
    assert antwoord.status_code == 403, (antwoord.status_code, antwoord.text)


async def test_the_name_of_another_tenant_is_unchanged_after_a_refused_update(
    unauthenticated_client: AsyncClient,
    opstelling: dict[str, object],
    postgres_session: AsyncSession,
) -> None:
    await unauthenticated_client.put(
        f"/api/v1/tenants/{_SLACHTOFFER_TENANT}",
        json={"name": "Overgenomen door tenant 2"},
        headers=_kopje(opstelling, "aanvaller"),
    )
    with TenantFilterBypass():
        naam = (
            await postgres_session.execute(
                text("SELECT name FROM tenants WHERE id = :t"), {"t": _SLACHTOFFER_TENANT}
            )
        ).scalar_one()
    assert naam == opstelling["naam_slachtoffer"]


async def test_a_tenant_admin_can_read_the_own_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    antwoord = await unauthenticated_client.get(
        f"/api/v1/tenants/{_AANVALLER_TENANT}", headers=_kopje(opstelling, "aanvaller")
    )
    assert (antwoord.status_code, antwoord.json().get("id")) == (
        200,
        _AANVALLER_TENANT,
    ), antwoord.text


async def test_a_tenant_admin_can_read_the_stats_of_the_own_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    antwoord = await unauthenticated_client.get(
        f"/api/v1/tenants/{_AANVALLER_TENANT}/stats", headers=_kopje(opstelling, "aanvaller")
    )
    assert antwoord.status_code == 200, (antwoord.status_code, antwoord.text)


async def test_a_platform_superuser_can_read_another_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    antwoord = await unauthenticated_client.get(
        f"/api/v1/tenants/{_AANVALLER_TENANT}", headers=_kopje(opstelling, "platform")
    )
    assert (antwoord.status_code, antwoord.json().get("id")) == (
        200,
        _AANVALLER_TENANT,
    ), antwoord.text
