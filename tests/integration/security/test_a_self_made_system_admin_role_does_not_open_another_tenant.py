"""Een tenantbeheerder kan zichzelf niet via een zelfgemaakte rol `system_admin` over de tenantgrens helpen.

Hypothese die hier getoetst wordt: `POST /api/rbac/roles/create` (recht `tenant:admin`) kent
geen lijst van gereserveerde rolnamen, en twee endpoints vertrouwen de ROLNAAM `system_admin`
voor cross-tenant toegang:

- `GET /api/v1/admin/digital-twin/stats?override_tenant_id=<id>`      (src/core/api/admin_digital_twin.py)
- `GET /admin/learning/tenants/{tenant_id}/llm-budget`                (src/core/api/admin_learning_endpoints.py)

Echte routes, echte JWT's, echte gebruikers en rollen in de testdatabase; de rol wordt NIET
rechtstreeks in de database gezet maar via de twee echte endpoints (`/api/rbac/roles/create` en
`/api/rbac/users/assign-role`) -- dat is het pad dat een aanvaller heeft.

Opstelling:
- tenant 2 ('Other Tenant'): de aanvaller, een gewone beheerder (rol `admin`, `*`/`*`, GEEN
  superuser) en 2 cognitieve profielen.
- tenant 1: het slachtoffer, 3 cognitieve profielen en een LLM-budget van 77/99 euro.
- platformbeheerder: een gebruiker van tenant 1 met de GESEEDE rol `system_admin` van tenant 1
  (door het platform ingericht, niet zelf gemaakt) -- de bedoelde uitzondering volgens de
  docstrings van beide endpoints. NB: de geseede superuser (gebruiker 1) is dat NIET: beide
  endpoints toetsen de rolnaam en niet `is_platform_superuser`, dus hij ziet bij
  `override_tenant_id` alleen zijn eigen tenant (gemeten, zie het rapport).

Verwacht productgedrag: de aanvaller ziet nooit data van tenant 1; de platformbeheerder wel
van tenant 2.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.jwt_handler import jwt_handler
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.learning.twin_models import TenantLLMBudget, UserCognitiveProfile

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.security]

_TENANT_AANVALLER = 2
_TENANT_SLACHTOFFER = 1
_PROFIELEN_SLACHTOFFER = 3
_PROFIELEN_AANVALLER = 2
_EMAIL = "aanvaller-tenant-2@lek.test"
_EMAIL_PLATFORM = "platformbeheerder-tenant-1@lek.test"
_STATS = "/api/v1/admin/digital-twin/stats"
_BUDGET = "/admin/learning/tenants/{tid}/llm-budget"


def _kop(user_id: int, email: str, tenant_id: int) -> dict[str, str]:
    token = jwt_handler.create_access_token(
        data={"sub": str(user_id), "user_id": user_id, "email": email, "tenant_id": tenant_id}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def opstelling(postgres_session: AsyncSession) -> AsyncIterator[dict[str, object]]:
    s = postgres_session
    maand = datetime.now(timezone.utc).strftime("%Y-%m")
    with TenantFilterBypass():
        rol_id = (
            await s.execute(
                text(
                    "INSERT INTO roles (name, tenant_id, is_active) VALUES ('admin', 2, true) "
                    "RETURNING id"
                )
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO role_permissions (role_id, tenant_id, resource, action) "
                "VALUES (:r, 2, '*', '*')"
            ),
            {"r": rol_id},
        )
        uid = (
            await s.execute(
                text(
                    "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
                    "VALUES (:e, 'x', true, false, 2) RETURNING id"
                ),
                {"e": _EMAIL},
            )
        ).scalar_one()
        await s.execute(
            text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)"),
            {"u": uid, "r": rol_id},
        )
        sys_rol_id = (
            await s.execute(text("SELECT id FROM roles WHERE name='system_admin' AND tenant_id=1"))
        ).scalar_one()
        pid = (
            await s.execute(
                text(
                    "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
                    "VALUES (:e, 'x', true, false, 1) RETURNING id"
                ),
                {"e": _EMAIL_PLATFORM},
            )
        ).scalar_one()
        await s.execute(
            text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)"),
            {"u": pid, "r": sys_rol_id},
        )
        for tid, aantal in (
            (_TENANT_SLACHTOFFER, _PROFIELEN_SLACHTOFFER),
            (_TENANT_AANVALLER, _PROFIELEN_AANVALLER),
        ):
            for i in range(aantal):
                s.add(UserCognitiveProfile(tenant_id=tid, human_user_id=f"h{tid}-{i}"))
        s.add(
            TenantLLMBudget(
                tenant_id=_TENANT_SLACHTOFFER,
                month=maand,
                budget_eur_soft=77.0,
                budget_eur_hard=99.0,
                spent_eur=0.0,
            )
        )
        await s.flush()
    yield {
        "aanvaller": _kop(uid, _EMAIL, _TENANT_AANVALLER),
        "aanvaller_id": uid,
        "platformbeheerder": _kop(pid, _EMAIL_PLATFORM, _TENANT_SLACHTOFFER),
    }


async def _maak_de_rol_en_koppel_hem(c: AsyncClient, o: dict[str, object]) -> None:
    """De aanval zoals een tenantbeheerder hem kan uitvoeren, over de echte endpoints."""
    kop = o["aanvaller"]
    assert isinstance(kop, dict)
    await c.post(
        "/api/rbac/roles/create",
        json={
            "name": "system_admin",
            "description": "zelfgemaakt",
            "permissions": [{"resource": "*", "action": "*"}],
        },
        headers=kop,
    )
    await c.post(
        "/api/rbac/users/assign-role",
        json={"user_id": o["aanvaller_id"], "role_name": "system_admin"},
        headers=kop,
    )


async def test_a_tenant_admin_cannot_create_a_role_named_system_admin(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    kop = opstelling["aanvaller"]
    assert isinstance(kop, dict)
    antwoord = await unauthenticated_client.post(
        "/api/rbac/roles/create",
        json={
            "name": "system_admin",
            "description": "zelfgemaakt",
            "permissions": [{"resource": "*", "action": "*"}],
        },
        headers=kop,
    )
    assert antwoord.status_code == 422, (antwoord.status_code, antwoord.text)


async def test_without_the_role_override_tenant_id_is_ignored_for_a_tenant_admin(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    """Controle (bedoeld GROEN): zonder de rol ziet de beheerder alleen zijn eigen tenant."""
    kop = opstelling["aanvaller"]
    assert isinstance(kop, dict)
    antwoord = await unauthenticated_client.get(
        f"{_STATS}?override_tenant_id={_TENANT_SLACHTOFFER}", headers=kop
    )
    assert (antwoord.status_code, antwoord.json()["data"]["profile_count"]) == (
        200,
        _PROFIELEN_AANVALLER,
    )


async def test_after_the_attack_the_digital_twin_stats_are_not_those_of_the_other_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    await _maak_de_rol_en_koppel_hem(unauthenticated_client, opstelling)
    kop = opstelling["aanvaller"]
    assert isinstance(kop, dict)
    antwoord = await unauthenticated_client.get(
        f"{_STATS}?override_tenant_id={_TENANT_SLACHTOFFER}", headers=kop
    )
    assert antwoord.json()["data"]["profile_count"] != _PROFIELEN_SLACHTOFFER, antwoord.text


async def test_after_the_attack_the_llm_budget_of_the_other_tenant_is_refused(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    await _maak_de_rol_en_koppel_hem(unauthenticated_client, opstelling)
    kop = opstelling["aanvaller"]
    assert isinstance(kop, dict)
    antwoord = await unauthenticated_client.get(
        _BUDGET.format(tid=_TENANT_SLACHTOFFER), headers=kop
    )
    assert antwoord.status_code == 403, (antwoord.status_code, antwoord.text)


async def test_without_the_role_the_llm_budget_of_the_other_tenant_is_refused(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    """Controle (bedoeld GROEN): `_enforce_tenant_access` doet zijn werk zolang de rol ontbreekt."""
    kop = opstelling["aanvaller"]
    assert isinstance(kop, dict)
    antwoord = await unauthenticated_client.get(
        _BUDGET.format(tid=_TENANT_SLACHTOFFER), headers=kop
    )
    assert antwoord.status_code == 403, (antwoord.status_code, antwoord.text)


async def test_a_provisioned_system_admin_may_read_the_digital_twin_stats_of_another_tenant(
    unauthenticated_client: AsyncClient, opstelling: dict[str, object]
) -> None:
    """Omgekeerde helft: een door het platform ingerichte system_admin blijft over de grens kunnen kijken."""
    kop = opstelling["platformbeheerder"]
    assert isinstance(kop, dict)
    antwoord = await unauthenticated_client.get(
        f"{_STATS}?override_tenant_id={_TENANT_AANVALLER}", headers=kop
    )
    assert (antwoord.status_code, antwoord.json()["data"]["profile_count"]) == (
        200,
        _PROFIELEN_AANVALLER,
    )
