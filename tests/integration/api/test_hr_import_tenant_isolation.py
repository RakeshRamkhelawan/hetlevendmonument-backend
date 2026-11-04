"""Tenant-isolatie-integratietest voor het hr-import-domein (Fase 3 dag 4, BE-AGT-061).

Bewijst tegen een ECHTE Postgres-database (niet SQLite) dat een skill/training die tenant A
importeert onzichtbaar is voor tenant B -- de repository-tests (dag 2) bewijzen dit al per
SQL-statement, maar niet over de volledige stack heen (echte HTTP-aanvraag, echte auth-
dependency-resolutie, echte DB-commit). Tenant 1's admin is al gezaaid door conftest.py; tenant
2 ("Other Tenant") bestaat al als rij maar heeft geen admin-gebruiker -- die zaait dit bestand
zelf, volgens hetzelfde patroon als conftest.py's eigen tenant-1-zaaiing (INSERT met ON CONFLICT
DO NOTHING via de ORM in plaats van ruwe SQL, want dit draait binnen de test-sessie's eigen
savepoint-transactie, niet in conftest.py's setup-connectie).

**Waarom een JWT met een ANDER tenant_id-claim niet volstaat.** Voor endpoints die de tenant
via de ambient ContextVar lezen (zoals `test_procedures_api.py::test_get_procedure_of_other_
tenant_404` toetst) is dat genoeg. Dit domein's `_resolve_tenant_id(current_user)` leest onder
TESTING=1 (die conftest.py altijd zet) `current_user.tenant_id` -- een verse databasekolom-
waarde uit `auth_service.get_user_by_id`, NIET de JWT-claim. Een gespoofde claim voor een
bestaande tenant-1-gebruiker zou dus gewoon tenant 1 blijven; er is een ECHTE tweede gebruiker
met tenant_id=2 in de database nodig.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from passlib.context import CryptContext
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.jwt_handler import jwt_handler
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.models.rbac_models import Role, RolePermission, User, user_roles

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest_asyncio.fixture
async def tenant_b_auth_headers(
    postgres_session: AsyncSession,
) -> AsyncGenerator[dict[str, str], None]:
    """Zaait een admin-gebruiker voor tenant 2 en retourneert diens Authorization-header.

    Tenant 2 zelf bestaat al (conftest.py); alleen de rol/gebruiker/koppeling ontbreken. Draait
    binnen `postgres_session`'s eigen savepoint-transactie, dus wordt na de test opgeruimd --
    geen aparte cleanup nodig.
    """
    with TenantFilterBypass():
        role = Role(name="admin", tenant_id=2, is_active=True)
        postgres_session.add(role)
        await postgres_session.flush()

        user = User(
            email="admin-tenant-b@integration.test",
            hashed_password=_pwd_context.hash("TenantBPass123!"),
            is_active=True,
            is_superuser=False,
            tenant_id=2,
        )
        postgres_session.add(user)
        await postgres_session.flush()

        await postgres_session.execute(insert(user_roles).values(user_id=user.id, role_id=role.id))
        postgres_session.add(RolePermission(role_id=role.id, tenant_id=2, resource="*", action="*"))
        await postgres_session.commit()

        token = jwt_handler.create_access_token(
            data={
                "sub": str(user.id),
                "user_id": user.id,
                "email": user.email,
                "tenant_id": 2,
                "scopes": ["admin:*"],
            }
        )
    yield {"Authorization": f"Bearer {token}"}


async def test_a_skill_imported_by_tenant_a_is_invisible_to_tenant_b(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    tenant_b_auth_headers: dict[str, str],
) -> None:
    import_response = await client.post(
        "/api/v1/hr/skills/import",
        data={"entity_type": "skill"},
        files={"file": ("skills.csv", b"name\nTenantAOnlySkill\n", "text/csv")},
        headers=admin_auth_headers,
    )
    assert import_response.status_code == 200
    assert import_response.json()["data"]["inserted"] == 1

    tenant_a_list = await client.get("/api/v1/hr/skills", headers=admin_auth_headers)
    assert tenant_a_list.status_code == 200
    tenant_a_names = {skill["name"] for skill in tenant_a_list.json()["data"]}
    assert "TenantAOnlySkill" in tenant_a_names

    tenant_b_list = await client.get("/api/v1/hr/skills", headers=tenant_b_auth_headers)
    assert tenant_b_list.status_code == 200
    tenant_b_names = {skill["name"] for skill in tenant_b_list.json()["data"]}
    assert "TenantAOnlySkill" not in tenant_b_names


async def test_a_training_imported_by_tenant_a_is_invisible_to_tenant_b(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    tenant_b_auth_headers: dict[str, str],
) -> None:
    import_response = await client.post(
        "/api/v1/hr/trainings/import",
        data={"entity_type": "training"},
        files={"file": ("trainings.csv", b"name\nTenantAOnlyTraining\n", "text/csv")},
        headers=admin_auth_headers,
    )
    assert import_response.status_code == 200
    assert import_response.json()["data"]["inserted"] == 1

    # Bewijst dat de GET-endpoint niet gewoon ALTIJD leeg teruggeeft (waardoor de assertie
    # hieronder vacuous zou zijn) -- tenant A moet zijn EIGEN training wel degelijk zien.
    tenant_a_list = await client.get("/api/v1/hr/trainings", headers=admin_auth_headers)
    assert tenant_a_list.status_code == 200
    tenant_a_names = {training["name"] for training in tenant_a_list.json()["data"]}
    assert "TenantAOnlyTraining" in tenant_a_names

    tenant_b_list = await client.get("/api/v1/hr/trainings", headers=tenant_b_auth_headers)
    assert tenant_b_list.status_code == 200
    tenant_b_names = {training["name"] for training in tenant_b_list.json()["data"]}
    assert "TenantAOnlyTraining" not in tenant_b_names
