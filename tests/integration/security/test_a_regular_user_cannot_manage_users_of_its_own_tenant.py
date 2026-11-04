"""Een gewone gebruiker beheert de gebruikers van de EIGEN tenant niet.

Aanvulling op `test_tenant_and_user_routes_refuse_a_foreign_tenant_id.py`: die toetst alleen de
grens TUSSEN tenants, en in `can_manage_users` komt die controle voor `has_role`. Daardoor bleef
de mutatie "has_role geeft altijd True" daar groen (13 passed). Hier gaat het om dezelfde tenant:
de gebruiker heeft de tenant, maar niet de beheerdersrol.

De rol van de gewone gebruiker krijgt bewust `*`/`*`: een andere permissiecontrole op de route kan
de 403 dus niet verklaren, alleen de rolcontrole in `can_manage_users`.

Lijst (GET /api/v1/users/) als gewone gebruiker: zie het blok (c) hieronder; gemeten is nu 500.

Hoofdletterongevoeligheid: `has_role` vergelijkt zonder letterhoogte, zoals `is_admin`. Dat is zo
gekozen omdat de gezaaide standaardrol `Admin` heet; `admin`, `Admin` en `TenantAdmin` zijn dus
allemaal beheerder, `user` niet.

Mutatiebewijs (op een kopie van shared.py): `has_role` geeft altijd True -> de weigertests worden
ROOD; `has_role` geeft altijd False -> de beheerdersbewijzen worden ROOD. Zie de commitboodschap
voor de uitslag per mutatie.

Autouse-fixtures (tests/conftest.py, tests/integration/conftest.py) zetten omgeving, singletons,
cache en rate limiter terug; geen ervan raakt rollen of `has_role`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.jwt_handler import jwt_handler
from src.core.database.tenant_query_filter import TenantFilterBypass

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.security]

_TENANT = 2
_WACHTWOORD = "Wachtwoord-123!"
ANDERE_EMAILS = [
    "admin@eigen.example.com",
    "hoofdletter@eigen.example.com",
    "tenantadmin@eigen.example.com",
]


def _kop(user_id: int, email: str) -> dict[str, str]:
    token = jwt_handler.create_access_token(
        data={"sub": str(user_id), "user_id": user_id, "email": email, "tenant_id": _TENANT}
    )
    return {"Authorization": f"Bearer {token}"}


async def _rol_id(s: AsyncSession, naam: str) -> int:
    bestaand = (
        await s.execute(
            text("SELECT id FROM roles WHERE name = :n AND tenant_id = :t"),
            {"n": naam, "t": _TENANT},
        )
    ).scalar_one_or_none()
    if bestaand is not None:
        return int(bestaand)
    rid = (
        await s.execute(
            text(
                "INSERT INTO roles (name, tenant_id, is_active) VALUES (:n, :t, true) RETURNING id"
            ),
            {"n": naam, "t": _TENANT},
        )
    ).scalar_one()
    await s.execute(
        text(
            "INSERT INTO role_permissions (role_id, tenant_id, resource, action) "
            "VALUES (:r, :t, '*', '*')"
        ),
        {"r": rid, "t": _TENANT},
    )
    return int(rid)


async def _maak_gebruiker(s: AsyncSession, email: str, rol: str | None) -> dict[str, str]:
    uid = (
        await s.execute(
            text(
                "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
                "VALUES (:e, 'x', true, false, :t) RETURNING id"
            ),
            {"e": email, "t": _TENANT},
        )
    ).scalar_one()
    if rol is not None:
        await s.execute(
            text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)"),
            {"u": uid, "r": await _rol_id(s, rol)},
        )
    return _kop(int(uid), email)


@pytest_asyncio.fixture
async def koppen(postgres_session: AsyncSession) -> AsyncIterator[dict[str, dict[str, str]]]:
    s = postgres_session
    with TenantFilterBypass():
        # De route maakt nieuwe gebruikers aan met de rol `user` van de doeltenant.
        await _rol_id(s, "user")
        uit = {
            "gewoon": await _maak_gebruiker(s, "gewoon@eigen.example.com", "user"),
            "zonder_rol": await _maak_gebruiker(s, "zonderrol@eigen.example.com", None),
            "admin": await _maak_gebruiker(s, "admin@eigen.example.com", "admin"),
            "Admin": await _maak_gebruiker(s, "hoofdletter@eigen.example.com", "Admin"),
            "TenantAdmin": await _maak_gebruiker(s, "tenantadmin@eigen.example.com", "TenantAdmin"),
        }
        await s.flush()
    yield uit


def _nieuw(email: str) -> dict[str, object]:
    return {"email": email, "password": _WACHTWOORD, "role_ids": []}


async def _aantal_met_email(s: AsyncSession, email: str) -> int:
    with TenantFilterBypass():
        rij = await s.execute(text("SELECT count(*) FROM users WHERE email = :e"), {"e": email})
        return int(rij.scalar_one())


# ------------------------------------------------------ weigeren: (a) rol user, (b) geen rol


async def test_a_user_with_role_user_cannot_create_a_user_in_the_own_tenant(
    unauthenticated_client: AsyncClient, koppen: dict[str, dict[str, str]]
) -> None:
    antwoord = await unauthenticated_client.post(
        f"/api/v1/users/?target_tenant_id={_TENANT}",
        json=_nieuw("nieuw-a@eigen.example.com"),
        headers=koppen["gewoon"],
    )
    assert antwoord.status_code == 403, (antwoord.status_code, antwoord.text)


async def test_nothing_is_stored_when_a_user_with_role_user_tries_to_create_a_user(
    unauthenticated_client: AsyncClient,
    koppen: dict[str, dict[str, str]],
    postgres_session: AsyncSession,
) -> None:
    await unauthenticated_client.post(
        f"/api/v1/users/?target_tenant_id={_TENANT}",
        json=_nieuw("nieuw-a2@eigen.example.com"),
        headers=koppen["gewoon"],
    )
    assert await _aantal_met_email(postgres_session, "nieuw-a2@eigen.example.com") == 0


async def test_a_user_without_roles_cannot_create_a_user_in_the_own_tenant(
    unauthenticated_client: AsyncClient, koppen: dict[str, dict[str, str]]
) -> None:
    antwoord = await unauthenticated_client.post(
        f"/api/v1/users/?target_tenant_id={_TENANT}",
        json=_nieuw("nieuw-b@eigen.example.com"),
        headers=koppen["zonder_rol"],
    )
    assert antwoord.status_code == 403, (antwoord.status_code, antwoord.text)


async def test_nothing_is_stored_when_a_user_without_roles_tries_to_create_a_user(
    unauthenticated_client: AsyncClient,
    koppen: dict[str, dict[str, str]],
    postgres_session: AsyncSession,
) -> None:
    await unauthenticated_client.post(
        f"/api/v1/users/?target_tenant_id={_TENANT}",
        json=_nieuw("nieuw-b2@eigen.example.com"),
        headers=koppen["zonder_rol"],
    )
    assert await _aantal_met_email(postgres_session, "nieuw-b2@eigen.example.com") == 0


# ------------------------------------------------------ (c) lijst: gewone gebruiker ziet geen anderen
#
# Gemeten gedrag (2026-10-04, commit 205fa549): GET /api/v1/users/ geeft voor een gewone gebruiker
# nu 500 (pydantic ValidationError: `UserResponse.model_validate(current_user)` krijgt het
# auth-UserResponse met rollen als tekst en zonder created_at). Bedoeld is 200 met alleen jezelf
# (zie de docstring van de route). Deze tests leggen daarom de VEILIGHEIDSEIS vast, die bij zowel
# het huidige 500 als de bedoelde 200 klopt: er staat geen ander gebruiker in het antwoord.


async def _lijst_tekst(client: AsyncClient, kop: dict[str, str]) -> str:
    # Het huidige 500 komt als uitzondering door de testtransport; dat telt als "geen antwoord met
    # andere gebruikers". Zodra de route 200 geeft, wordt de antwoordtekst getoetst.
    try:
        antwoord = await client.get("/api/v1/users/", headers=kop)
    except ValidationError as fout:
        return f"geen antwoord, route faalt met {type(fout).__name__}"
    return antwoord.text


async def test_a_regular_user_does_not_get_other_users_in_the_user_list(
    unauthenticated_client: AsyncClient, koppen: dict[str, dict[str, str]]
) -> None:
    tekst = await _lijst_tekst(unauthenticated_client, koppen["gewoon"])
    assert [e for e in ANDERE_EMAILS if e in tekst] == [], tekst


async def test_a_user_without_roles_does_not_get_other_users_in_the_user_list(
    unauthenticated_client: AsyncClient, koppen: dict[str, dict[str, str]]
) -> None:
    tekst = await _lijst_tekst(unauthenticated_client, koppen["zonder_rol"])
    assert [e for e in ANDERE_EMAILS if e in tekst] == [], tekst


async def test_a_tenant_admin_sees_all_users_of_the_own_tenant_in_the_list(
    unauthenticated_client: AsyncClient, koppen: dict[str, dict[str, str]]
) -> None:
    antwoord = await unauthenticated_client.get("/api/v1/users/", headers=koppen["admin"])
    emails = {u["email"] for u in antwoord.json()["data"]}
    assert {
        "gewoon@eigen.example.com",
        "zonderrol@eigen.example.com",
        "admin@eigen.example.com",
    } <= emails, antwoord.text


_ANDERE_TENANT_EMAIL = "vreemd@andere-tenant.example.com"


async def test_a_regular_user_gets_a_list_with_only_the_user_itself(
    unauthenticated_client: AsyncClient,
    koppen: dict[str, dict[str, str]],
    postgres_session: AsyncSession,
) -> None:
    """Bedoeld gedrag (docstring van de route): 200 en alleen jezelf.

    Anders dan de weigertests hierboven pint deze test het 500 NIET: een lijst die faalt is voor
    een klant geen lijst. Ook een gebruiker van een andere tenant staat erbij (tenant 1), zodat
    "alleen jezelf" ook een tenantgrens toetst.
    """
    with TenantFilterBypass():
        await postgres_session.execute(
            text(
                "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
                "VALUES (:e, 'x', true, false, 1)"
            ),
            {"e": _ANDERE_TENANT_EMAIL},
        )
        await postgres_session.flush()
    try:
        antwoord = await unauthenticated_client.get("/api/v1/users/", headers=koppen["gewoon"])
    except ValidationError as fout:
        pytest.fail(f"de lijstroute faalt met {type(fout).__name__}: {fout}")
    emails = [u["email"] for u in antwoord.json()["data"]] if antwoord.status_code == 200 else None
    assert (antwoord.status_code, emails) == (200, ["gewoon@eigen.example.com"]), antwoord.text


# ------------------------------------------------------ (d) groene helften


@pytest.mark.parametrize("rol", ["admin", "Admin", "TenantAdmin"])
async def test_a_tenant_admin_can_create_a_user_in_the_own_tenant(
    unauthenticated_client: AsyncClient,
    koppen: dict[str, dict[str, str]],
    postgres_session: AsyncSession,
    rol: str,
) -> None:
    # `Admin` (hoofdletter) telt mee omdat de gezaaide standaardrol zo heet; `has_role` is
    # hoofdletterongevoelig, net als `is_admin`.
    email = f"nieuw-{rol.lower()}@eigen.example.com"
    antwoord = await unauthenticated_client.post(
        f"/api/v1/users/?target_tenant_id={_TENANT}",
        json=_nieuw(email),
        headers=koppen[rol],
    )
    assert (antwoord.status_code, await _aantal_met_email(postgres_session, email)) == (
        201,
        1,
    ), antwoord.text
