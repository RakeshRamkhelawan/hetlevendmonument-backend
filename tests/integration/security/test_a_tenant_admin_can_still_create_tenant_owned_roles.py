"""De gereserveerde rolnaam `system_admin` is dicht, maar tenant-eigen rollen blijven aanmaakbaar.

Een bewaker die alleen weigert, mag niet kunnen slagen door te veel te weigeren. Deze tests
bewaken de andere helft van `test_a_self_made_system_admin_role_does_not_open_another_tenant.py`:

- een tenantbeheerder (rol `beheerder` met `*`/`*`, GEEN superuser, tenant 2) maakt over de echte
  route `POST /api/rbac/roles/create` de rollen `admin` en `tenantadmin` aan en krijgt 200;
- lookalikes van `system_admin` (hoofdletters, spaties, vol-breedtetekens die onder NFKC gelijk
  worden) worden geweigerd met 422 en komen niet in de tabel `roles` terecht.

De beheerder zelf heet NIET `admin`, anders botst de rol die hij aanmaakt op zijn eigen rol (409)
en zou de test het verkeerde meten.

Mutatiebewijs (op een KOPIE van de boom, nooit in de werkboom):
- `RESERVED_ROLE_NAMES` uitgebreid met `admin`            -> test_..._admin_... wordt ROOD (422).
- `RESERVED_ROLE_NAMES` uitgebreid met `tenantadmin`      -> test_..._tenantadmin_... wordt ROOD.
- NFKC weggelaten, `.strip().casefold()` gehouden         -> alleen de vol-breedte-variant ROOD.
- `.strip()` weggelaten                                    -> alleen de variant met spaties ROOD.
- `.casefold()` weggelaten                                 -> alleen `System_Admin` ROOD.
- gereserveerde naam helemaal niet gecontroleerd (de oorspronkelijke toestand) -> alle lookalikes
  en `system_admin` zelf ROOD (200 in plaats van 422).
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

_TENANT = 2
_EMAIL = "tenantbeheerder-2@rollen.test"
_CREATE = "/api/rbac/roles/create"
_VOL_BREEDTE = "".join(chr(ord(c) + 0xFEE0) if c != "_" else "\uff3f" for c in "system_admin")


@pytest_asyncio.fixture
async def beheerder_header(postgres_session: AsyncSession) -> AsyncIterator[dict[str, str]]:
    s = postgres_session
    with TenantFilterBypass():
        rol_id = (
            await s.execute(
                text(
                    "INSERT INTO roles (name, tenant_id, is_active) VALUES ('beheerder', :t, true) "
                    "RETURNING id"
                ),
                {"t": _TENANT},
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO role_permissions (role_id, tenant_id, resource, action) "
                "VALUES (:r, :t, '*', '*')"
            ),
            {"r": rol_id, "t": _TENANT},
        )
        uid = (
            await s.execute(
                text(
                    "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
                    "VALUES (:e, 'x', true, false, :t) RETURNING id"
                ),
                {"e": _EMAIL, "t": _TENANT},
            )
        ).scalar_one()
        await s.execute(
            text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)"),
            {"u": uid, "r": rol_id},
        )
        await s.flush()
    token = jwt_handler.create_access_token(
        data={"sub": str(uid), "user_id": uid, "email": _EMAIL, "tenant_id": _TENANT}
    )
    yield {"Authorization": f"Bearer {token}"}


async def _maak(c: AsyncClient, kop: dict[str, str], naam: str):  # noqa: ANN202
    return await c.post(
        _CREATE,
        json={
            "name": naam,
            "description": "test",
            "permissions": [{"resource": "agent", "action": "read"}],
        },
        headers=kop,
    )


async def test_a_tenant_admin_can_create_the_role_admin(
    unauthenticated_client: AsyncClient, beheerder_header: dict[str, str]
) -> None:
    antwoord = await _maak(unauthenticated_client, beheerder_header, "admin")
    assert (antwoord.status_code, antwoord.json().get("name")) == (200, "admin"), antwoord.text


async def test_a_tenant_admin_can_create_the_role_tenantadmin(
    unauthenticated_client: AsyncClient, beheerder_header: dict[str, str]
) -> None:
    antwoord = await _maak(unauthenticated_client, beheerder_header, "tenantadmin")
    assert (antwoord.status_code, antwoord.json().get("name")) == (200, "tenantadmin"), antwoord.text


@pytest.mark.parametrize(
    "naam",
    ["system_admin", "System_Admin", " system_admin ", _VOL_BREEDTE],
    ids=["exact", "hoofdletters", "spaties", "vol-breedte"],
)
async def test_a_lookalike_of_the_reserved_name_is_refused_with_422(
    unauthenticated_client: AsyncClient, beheerder_header: dict[str, str], naam: str
) -> None:
    antwoord = await _maak(unauthenticated_client, beheerder_header, naam)
    assert antwoord.status_code == 422, (antwoord.status_code, antwoord.text)


@pytest.mark.parametrize(
    "naam",
    ["System_Admin", " system_admin ", _VOL_BREEDTE],
    ids=["hoofdletters", "spaties", "vol-breedte"],
)
async def test_a_refused_lookalike_is_not_stored(
    unauthenticated_client: AsyncClient,
    beheerder_header: dict[str, str],
    postgres_session: AsyncSession,
    naam: str,
) -> None:
    await _maak(unauthenticated_client, beheerder_header, naam)
    with TenantFilterBypass():
        aantal = (
            await postgres_session.execute(
                text("SELECT count(*) FROM roles WHERE tenant_id = :t AND name = :n"),
                {"t": _TENANT, "n": naam},
            )
        ).scalar_one()
    assert aantal == 0
