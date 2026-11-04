"""De feature-schakelaar van een tenant is niet door een beheerder van een andere tenant te zetten.

Route: `POST /api/admin/features/{feature}/toggle?target_tenant_id=<id>`
(`src/core/api/v1/feature_flags/admin_router.py`). De route neemt de DOEL-tenant uit een
queryparameter en schrijft onder `TenantFilterBypass`. De vraag is of `require_admin` (een
rolnaamcontrole BINNEN de eigen tenant) genoeg is.

Waarom deze module bestaat naast `test_feature_flag_security.py`: de bestaande
`test_toggle_feature_admin_success` gebruikt de `admin_token` van tenant 1 (een superuser) tegen
tenant 101 en slaagt dus ook bij een lek. Hij onderscheidt de beheerder van een andere tenant niet
van een platformbeheerder.

Echte route, echte JWT, echte gebruikers en rollen in de testdatabase (geen
`get_current_user`-override). De drie spelers:

- tenant-1-beheerder: gewone gebruiker van tenant 1, rol `admin` van tenant 1, GEEN superuser.
- platformbeheerder: de geseede gebruiker 1 (`is_superuser`, tenant 1).
- tenant 2: de geseede 'Other Tenant', met een eigen rij `feature_flags`.

Verwacht (productgedrag): de tenant-1-beheerder krijgt 403 voor tenant 2 en de rij van tenant 2
blijft ongewijzigd; de platformbeheerder mag wel; de tenant-1-beheerder mag zijn EIGEN tenant.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.jwt_handler import jwt_handler
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.feature_flags.models import FeatureFlag

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.security]

_FEATURE = "memory_mcp"
_URL = "/api/admin/features/" + _FEATURE + "/toggle"
_TENANT_EIGEN = 1
_TENANT_ANDER = 2
_EMAIL_TENANTBEHEERDER = "tenantbeheerder-1@lek.test"


def _kop(user_id: int, email: str, tenant_id: int) -> dict[str, str]:
    token = jwt_handler.create_access_token(
        data={"sub": str(user_id), "user_id": user_id, "email": email, "tenant_id": tenant_id}
    )
    return {"Authorization": f"Bearer {token}"}


async def _lees_vlag(sessie: AsyncSession, tenant_id: int) -> bool | None:
    with TenantFilterBypass():
        await sessie.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant_id)}
        )
        res = await sessie.execute(
            select(FeatureFlag.is_enabled).where(
                FeatureFlag.tenant_id == tenant_id, FeatureFlag.feature_name == _FEATURE
            )
        )
        return res.scalar_one_or_none()


@pytest_asyncio.fixture
async def opstelling(postgres_session: AsyncSession) -> AsyncIterator[dict[str, dict[str, str]]]:
    """Tenantbeheerder (niet-superuser) en een vlag van tenant 2 die UIT staat."""
    sessie = postgres_session
    with TenantFilterBypass():
        rol_id = (
            await sessie.execute(text("SELECT id FROM roles WHERE name='admin' AND tenant_id=1"))
        ).scalar_one()
        gebruiker_id = (
            await sessie.execute(
                text(
                    "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
                    "VALUES (:e, 'x', true, false, 1) RETURNING id"
                ),
                {"e": _EMAIL_TENANTBEHEERDER},
            )
        ).scalar_one()
        await sessie.execute(
            text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)"),
            {"u": gebruiker_id, "r": rol_id},
        )
        await sessie.execute(
            text("SELECT set_config('app.current_tenant', '2', true)"),
        )
        sessie.add(FeatureFlag(tenant_id=_TENANT_ANDER, feature_name=_FEATURE, is_enabled=False))
        await sessie.flush()
    yield {
        "tenantbeheerder": _kop(gebruiker_id, _EMAIL_TENANTBEHEERDER, _TENANT_EIGEN),
        "platformbeheerder": _kop(1, "admin@integration.test", _TENANT_EIGEN),
    }


async def test_a_tenant_admin_cannot_toggle_the_flag_of_another_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, dict[str, str]]
) -> None:
    antwoord = await unauthenticated_client.post(
        f"{_URL}?target_tenant_id={_TENANT_ANDER}",
        json={"enabled": True},
        headers=opstelling["tenantbeheerder"],
    )
    assert antwoord.status_code == 403, (antwoord.status_code, antwoord.text)


async def test_the_flag_of_the_other_tenant_is_unchanged_after_the_attempt(
    unauthenticated_client: AsyncClient,
    postgres_session: AsyncSession,
    opstelling: dict[str, dict[str, str]],
) -> None:
    await unauthenticated_client.post(
        f"{_URL}?target_tenant_id={_TENANT_ANDER}",
        json={"enabled": True},
        headers=opstelling["tenantbeheerder"],
    )
    assert await _lees_vlag(postgres_session, _TENANT_ANDER) is False


async def test_a_platform_superuser_may_toggle_the_flag_of_another_tenant(
    unauthenticated_client: AsyncClient,
    postgres_session: AsyncSession,
    opstelling: dict[str, dict[str, str]],
) -> None:
    antwoord = await unauthenticated_client.post(
        f"{_URL}?target_tenant_id={_TENANT_ANDER}",
        json={"enabled": True},
        headers=opstelling["platformbeheerder"],
    )
    assert (antwoord.status_code, await _lees_vlag(postgres_session, _TENANT_ANDER)) == (200, True)


async def test_a_tenant_admin_may_toggle_the_flag_of_its_own_tenant(
    unauthenticated_client: AsyncClient,
    postgres_session: AsyncSession,
    opstelling: dict[str, dict[str, str]],
) -> None:
    antwoord = await unauthenticated_client.post(
        f"{_URL}?target_tenant_id={_TENANT_EIGEN}",
        json={"enabled": True},
        headers=opstelling["tenantbeheerder"],
    )
    assert (antwoord.status_code, await _lees_vlag(postgres_session, _TENANT_EIGEN)) == (200, True)
