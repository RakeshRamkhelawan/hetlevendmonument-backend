"""Zelfregistratie zonder token maakt een EIGEN, gescheiden omgeving (SP-KLANT-01 dag 1).

**De bevinding (gemeten door de verkenner op 549f385b, en hier opnieuw).** `POST
/api/v1/auth/register` zonder token geeft 400 "Tenant context required for registration":
een bezoeker zonder inlog heeft geen tenant, en niets maakt er een aan. Een nieuwe klant komt
dus niet verder dan het formulier (meetlat scenario 1 stap 2: de tenant hoort automatisch
te worden aangemaakt).

**Het besluit dat deze tests vastleggen (brief, "Het besluit" punt 1).** Registratie zonder
token maakt een tenant, zaait de standaardrollen van die tenant en geeft de eerste gebruiker
de rol `admin`. De tenant komt uit de NIEUWE rij en NOOIT uit het verzoek.

**Echte app, echte rijen.** `create_test_app()`, echte JWT's uit `/auth/login`, rijen terug
gelezen met een aparte verbinding (zie `_voordeur_hulp.py`). De isolatie is hier aan de
APPLICATIEKANT bewezen met TWEE echte tenants. De test-PostgreSQL verbindt als `postgres` en
omzeilt RLS; de meting onder de applicatierol hoort bij OP-151.

**ROOD zolang het pad niet bestaat** (elke test hieronder zonder `groen` in de naam of in
de docstring): de registratie geeft 400, dus er is geen tenant, geen rol en geen admin.

**GROEN, en dat is de bedoeling** (de omgekeerde helft; zonder deze is "weiger alles" of
"zet iedereen in tenant 1" een geldige oplossing):
- `test_without_a_token_the_agents_and_workflows_endpoints_refuse` (200 komt niet uit open
  endpoints),
- `test_an_admin_can_still_add_a_user_to_his_own_tenant` (het ENIGE legitieme pad naar een
  bestaande tenant blijft werken),
- `test_registering_an_existing_email_is_refused_and_leaves_no_tenant_behind`,
- `test_a_burst_of_registrations_is_throttled` (de bestaande limiter blijft staan),
- `test_a_foreign_tenant_in_the_body_never_lands_the_user_there` voor de body-varianten die
  vandaag al door `extra="forbid"` worden geweigerd.

**Mutatiebewijs.** Er bestaat op het moment van schrijven GEEN registratiepad om te muteren;
daarom is het bewijs geleverd tegen een wegwerp-referentie-implementatie in een KOPIE van de
boom (niet in de repo). Zie het rapport van de testspecialist; per bewaakt element:
- tenant uit header/query/body vertrouwen -> `test_a_foreign_tenant_*` ROOD
- altijd tenant 1 gebruiken -> `test_two_self_registrations_*` en `test_a_foreign_tenant_*` ROOD
- rollen niet zaaien -> `test_the_new_tenant_has_the_default_roles` en de 200-tests ROOD
- eerste gebruiker geen `admin` -> `test_the_first_user_is_admin_of_the_new_tenant` en
  de 200-tests ROOD
- limiter weghalen -> `test_a_burst_of_registrations_is_throttled` ROOD
- bestaand e-mailadres toelaten -> `test_registering_an_existing_email_*` ROOD
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from src.core.auth.jwt_handler import jwt_handler
from tests.integration.security._voordeur_hulp import (  # noqa: F401  (fixtures)
    BESTAANDE_TENANTS,
    bearer,
    client,
    een_waarde,
    limiters_leeg,
    log_in,
    registreer,
    rijen,
    rolnamen_van_gebruiker,
    rolnamen_van_tenant,
    tenant_ids,
    tenant_van_gebruiker,
    unieke_email,
)

pytestmark = [pytest.mark.integration, pytest.mark.security]


async def _registreer_en_geef_tenant(client: AsyncClient, email: str) -> int:
    r = await registreer(client, email)
    assert r.status_code == 201, f"registreren gaf {r.status_code}: {r.text}"
    return int(r.json()["tenant_id"])


# --------------------------------------------------------------------------------------
# Wat de registratie aanmaakt
# --------------------------------------------------------------------------------------


async def test_registration_without_a_token_creates_a_new_tenant(client: AsyncClient) -> None:
    ervoor = tenant_ids()
    email = unieke_email()

    tenant_id = await _registreer_en_geef_tenant(client, email)

    assert tenant_id not in ervoor and tenant_id in tenant_ids()


async def test_the_new_tenant_has_the_default_roles(client: AsyncClient) -> None:
    tenant_id = await _registreer_en_geef_tenant(client, unieke_email())

    assert {"admin", "user"} <= rolnamen_van_tenant(tenant_id)


async def test_the_first_user_is_admin_of_the_new_tenant(client: AsyncClient) -> None:
    email = unieke_email()
    await _registreer_en_geef_tenant(client, email)

    assert rolnamen_van_gebruiker(email) == {"admin"}


async def test_the_first_user_lives_in_the_new_tenant_and_nowhere_else(
    client: AsyncClient,
) -> None:
    email = unieke_email()
    tenant_id = await _registreer_en_geef_tenant(client, email)

    assert tenant_van_gebruiker(email) == [tenant_id]


@pytest.mark.parametrize("pad", ["/api/v1/agents/", "/api/v1/workflows/"])
async def test_the_new_admin_is_not_refused_on_agents_and_workflows(
    client: AsyncClient, pad: str
) -> None:
    """Een beheerder zonder rol kreeg overal 403 (brief: 'Een beheerder zonder rol')."""
    email = unieke_email()
    await _registreer_en_geef_tenant(client, email)
    token = await log_in(client, email)

    r = await client.get(pad, headers=bearer(token))

    assert r.status_code == 200, f"{pad} gaf {r.status_code}: {r.text}"


@pytest.mark.parametrize("pad", ["/api/v1/agents/", "/api/v1/workflows/"])
async def test_without_a_token_the_agents_and_workflows_endpoints_refuse(
    client: AsyncClient, pad: str
) -> None:
    """GROEN: de omgekeerde helft van de 200-test. Het 200 komt niet uit een open endpoint."""
    r = await client.get(pad)

    assert r.status_code == 401


# --------------------------------------------------------------------------------------
# Twee klanten, twee gescheiden omgevingen
# --------------------------------------------------------------------------------------


async def test_two_self_registrations_give_two_separate_tenants(client: AsyncClient) -> None:
    eerste = await _registreer_en_geef_tenant(client, unieke_email("a"))
    tweede = await _registreer_en_geef_tenant(client, unieke_email("b"))

    assert eerste != tweede


async def test_each_new_tenant_holds_exactly_its_own_user(client: AsyncClient) -> None:
    email_a, email_b = unieke_email("a"), unieke_email("b")
    tenant_a = await _registreer_en_geef_tenant(client, email_a)
    tenant_b = await _registreer_en_geef_tenant(client, email_b)

    telling = {
        t: een_waarde("SELECT count(*) FROM users WHERE tenant_id = :t", t=t)
        for t in (tenant_a, tenant_b)
    }
    assert telling == {tenant_a: 1, tenant_b: 1}


async def _rol_ids_via_api(client: AsyncClient, email: str) -> set[int]:
    """Wat een beheerder via de API aan rollen ziet (`GET /api/rbac/roles`, tenantgebonden).

    Bewust NIET `GET /api/v1/users/`: dat geeft 500 voor elke niet-superuser-beheerder
    (`users/shared.py:15` verwacht rolobjecten, het token levert tekst). Gemeten twee keer,
    ook op de ongewijzigde boom met een via een uitnodiging aangemaakte beheerder; zie het
    rapport. Dat is een apart defect en geen onderdeel van dit verzoek.
    """
    r = await client.get("/api/rbac/roles", headers=bearer(await log_in(client, email)))
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    return {int(rol["id"]) for rol in r.json()}


async def test_the_second_customer_sees_nothing_of_the_first_through_the_api(
    client: AsyncClient,
) -> None:
    email_a, email_b = unieke_email("a"), unieke_email("b")
    tenant_a = await _registreer_en_geef_tenant(client, email_a)
    await _registreer_en_geef_tenant(client, email_b)
    rollen_van_a = {
        int(r[0]) for r in rijen("SELECT id FROM roles WHERE tenant_id = :t", t=tenant_a)
    }

    gezien_door_b = await _rol_ids_via_api(client, email_b)

    assert rollen_van_a and not (gezien_door_b & rollen_van_a)


async def test_a_new_admin_does_see_his_own_roles_through_the_api(client: AsyncClient) -> None:
    """De omgekeerde helft van de test hierboven: 'toon niets' mag niet slagen."""
    email_a, email_b = unieke_email("a"), unieke_email("b")
    await _registreer_en_geef_tenant(client, email_a)
    tenant_b = await _registreer_en_geef_tenant(client, email_b)
    eigen = {int(r[0]) for r in rijen("SELECT id FROM roles WHERE tenant_id = :t", t=tenant_b)}

    gezien_door_b = await _rol_ids_via_api(client, email_b)

    assert eigen and gezien_door_b == eigen


# --------------------------------------------------------------------------------------
# Registratie plaatst NOOIT iemand in een BESTAANDE tenant
# --------------------------------------------------------------------------------------

_VREEMDE_TENANT_VIA_HEADER_OF_QUERY = [
    pytest.param({"headers": {"X-Tenant-ID": "1"}}, id="header-X-Tenant-ID"),
    pytest.param({"headers": {"X-Tenant-Slug": "default"}}, id="header-slug"),
    pytest.param({"params": {"tenant_id": "1"}}, id="query-tenant_id"),
    pytest.param({"params": {"tenant": "default"}}, id="query-tenant-slug"),
    pytest.param(
        {"headers": {"Authorization": "Bearer niet-een-echt-token"}}, id="header-ongeldig-token"
    ),
]


@pytest.mark.parametrize("vorm", _VREEMDE_TENANT_VIA_HEADER_OF_QUERY)
async def test_a_foreign_tenant_in_header_or_query_is_ignored(
    client: AsyncClient, vorm: dict[str, dict[str, str]]
) -> None:
    """Header en query zijn geen bron van de tenant: de nieuwe klant krijgt een EIGEN tenant."""
    email = unieke_email()

    r = await registreer(client, email, **vorm)

    assert r.status_code == 201, f"{r.status_code}: {r.text}"
    assert tenant_van_gebruiker(email) and not set(tenant_van_gebruiker(email)) & set(
        BESTAANDE_TENANTS
    )


_VREEMDE_TENANT_VIA_BODY = [
    pytest.param({"tenant_id": 1}, id="body-tenant_id"),
    pytest.param({"tenant_slug": "default"}, id="body-tenant_slug"),
    pytest.param({"slug": "default"}, id="body-slug"),
    pytest.param({"organization": "Default Tenant"}, id="body-organization"),
    pytest.param({"organisation": "Default Tenant"}, id="body-organisation"),
    pytest.param({"organisatie": "Default Tenant"}, id="body-organisatie"),
    pytest.param({"company": "Default Tenant"}, id="body-company"),
]


@pytest.mark.parametrize("extra", _VREEMDE_TENANT_VIA_BODY)
async def test_a_foreign_tenant_in_the_body_never_lands_the_user_there(
    client: AsyncClient, extra: dict[str, object]
) -> None:
    """Geweigerd (4xx) is goed, en een eigen nieuwe tenant is goed; tenant 1 of 2 nooit.

    De uitkomst is bewust een van twee: de brief laat open of er een organisatieveld komt
    (vraag voor Rakesh). Vast staat alleen dat NIETS in het verzoek de gebruiker in een
    bestaande tenant brengt, ook niet als het veld de naam van een bestaande tenant draagt.
    """
    email = unieke_email()

    r = await registreer(client, email, extra_body=extra)

    assert not set(tenant_van_gebruiker(email)) & set(BESTAANDE_TENANTS)
    assert r.status_code in (201, 400, 409, 422), f"{r.status_code}: {r.text}"


async def test_an_admin_can_still_add_a_user_to_his_own_tenant(client: AsyncClient) -> None:
    """GROEN: het ENIGE legitieme pad naar een bestaande tenant is een uitnodiging door een
    beheerder, en dat blijft werken. Zonder deze helft is 'weiger elke schrijfactie' geldig."""
    admin = jwt_handler.create_access_token(
        data={
            "sub": "1",
            "user_id": 1,
            "email": "admin@integration.test",
            "tenant_id": 1,
            "scopes": ["admin:*"],
        }
    )
    email = unieke_email("uitgenodigd")

    r = await client.post(
        "/api/v1/users/",
        params={"target_tenant_id": 1},
        json={"email": email, "password": "GeldigWachtwoord1"},
        headers=bearer(admin),
    )

    assert r.status_code == 201 and tenant_van_gebruiker(email) == [1], f"{r.status_code}: {r.text}"


async def test_registering_an_existing_email_is_refused_and_leaves_no_tenant_behind(
    client: AsyncClient,
) -> None:
    """GROEN vandaag (400 om een andere reden), en het blijft de grens zodra het pad bestaat.

    Aanname van de testspecialist, NIET uit de brief: `users.email` is alleen uniek per
    tenant, maar inloggen zoekt platformbreed op e-mail. Een tweede account met hetzelfde
    adres in een eigen tenant maakt inloggen dubbelzinnig (overnamerisico). Het adres
    `admin@example.com` bestaat in tenant 1 (gezaaid door `reset_db_per_module`; het adres
    `admin@integration.test` is onbruikbaar, de e-mailvalidatie weigert het TLD `.test`). De registratie moet dus weigeren, zonder
    een lege tenant achter te laten (geen halve aanmaak) en zonder het bestaan te verraden
    (zelfde neutrale melding als `test_registratie_lekt_geen_bestaan.py`).
    """
    ervoor = tenant_ids()

    r = await registreer(client, "admin@example.com")

    assert r.status_code == 400 and tenant_ids() == ervoor
    assert "exist" not in r.text.lower()


# --------------------------------------------------------------------------------------
# Misbruikgrens
# --------------------------------------------------------------------------------------


async def test_the_first_registrations_are_not_throttled(client: AsyncClient) -> None:
    """De legitieme helft: een echte nieuwe klant komt er gewoon door (ook de tweede)."""
    statussen = [(await registreer(client, unieke_email())).status_code for _ in range(2)]

    assert statussen == [201, 201]


async def test_a_burst_of_registrations_is_throttled(client: AsyncClient) -> None:
    """Een salvo van 12 verzoeken vanaf een adres haalt een 429, en de afgewezen verzoeken
    laten geen tenant achter. De limiter is `auth_limiter` (3/minuut, slowapi); de brief
    noemt `rate_limiter.py` en ook die staat in `limiters_leeg`. Welke limiter het wordt is
    een keuze van de bouwer; het gedrag is wat hier bewaakt wordt."""
    ervoor = tenant_ids()

    statussen = [(await registreer(client, unieke_email())).status_code for _ in range(12)]

    nieuw = len(tenant_ids() - ervoor)
    assert 429 in statussen
    assert nieuw == statussen.count(201), f"{statussen} maar {nieuw} nieuwe tenants"


async def test_the_users_are_not_in_tenant_one_after_a_burst(client: AsyncClient) -> None:
    """Eigenschap van het hele salvo: niemand van de aanmelders staat in een bestaande tenant."""
    emails = [unieke_email() for _ in range(6)]

    for e in emails:
        await registreer(client, e)

    in_bestaand = [e for e in emails if set(tenant_van_gebruiker(e)) & set(BESTAANDE_TENANTS)]
    assert in_bestaand == []
