"""Tokens intrekken en uitloggen, gemeten over de echte voordeur (beveiligingsnazorg, 2026-10-14).

Brief `docs/agent-briefs/generated/2026-10-14-sprint-dag-beveiligingsnazorg-tokens-en-avg-status.md`.
Vervolg op `tests/integration/security/test_een_uitgelogd_token_wordt_geweigerd.py`, die bewijst
dat het ACCESS-token na uitloggen faalt. Hier de vier dingen die die test niet raakt:

1. `POST /auth/revoke` trekt een token in: van wie mag dat? Tot nu toe van IEDEREEN met een geldig
   token, ook van een andere medewerker of een andere tenant. De blacklistrij kreeg bovendien het id
   van de AANVRAGER als eigenaar in plaats van dat van de houder van het token.
2. Uitloggen terwijl het intrekken faalt mag niet "gelukt" melden.
3. Uitloggen trekt ook het REFRESH-token in: anders krijgt wie het gekopieerd heeft na het
   uitloggen gewoon een nieuw access-token.
4. Het refresh-token dat een ander toebehoort, wordt via jouw uitloggen niet ingetrokken.

**Tegenrichtingen, met opzet.** Zonder de groene gevallen (eigen token, beheerder van dezelfde
tenant) is "weiger altijd" een geldige oplossing van 1.

**Wat deze test NIET zegt.** De test-PostgreSQL verbindt als `postgres` en omzeilt Row Level
Security. Het refresh-token van een sessie die VOOR deze wijziging is gestart, zit in een cookie met
het oude pad en komt niet bij `/auth/logout`; dat is niet gemeten en niet te repareren zonder
sessietabel.

**Draaien:** zet de testdatabase expliciet (`tests/fixtures/testdatabase.py`) en `REDIS_URL` (het
CSRF-token komt uit Redis), en draai daarna `pytest tests/integration/test_beveiligingsnazorg_tokens.py`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from tests.integration.security._voordeur_hulp import (  # noqa: F401  (fixtures)
    WACHTWOORD,
    bearer,
    client,
    een_waarde,
    limiters_leeg,
    log_in,
    registreer,
    rijen,
    unieke_email,
    voer_uit,
)

pytestmark = [pytest.mark.integration, pytest.mark.security]

_INGANG = "/api/v1/auth/me"
_GEWEIGERD = (403, 404)


async def _beheerder(client: AsyncClient, voorvoegsel: str) -> tuple[str, str]:
    """Registreren maakt een EIGEN tenant met de registrant als beheerder."""
    email = unieke_email(voorvoegsel)
    r = await registreer(client, email)
    assert r.status_code == 201, f"registreren gaf {r.status_code}: {r.text}"
    return email, await log_in(client, email)


async def _medewerker(
    client: AsyncClient, beheerder_email: str, voorvoegsel: str
) -> tuple[str, str]:
    """Een gewone medewerker in DEZELFDE tenant als de beheerder, zonder beheerdersrol.

    Het wachtwoord is dat van de beheerder (zelfde hash), zodat de gebruiker echt kan inloggen.
    """
    email = unieke_email(voorvoegsel)
    voer_uit(
        "INSERT INTO users (email, hashed_password, is_active, is_superuser, tenant_id) "
        "SELECT :e, hashed_password, true, false, tenant_id FROM users WHERE email = :b",
        e=email,
        b=beheerder_email,
    )
    return email, await log_in(client, email)


async def _trek_in(client: AsyncClient, aanvrager_token: str, doel_token: str) -> int:
    r = await client.post(
        "/api/v1/auth/revoke", json={"token": doel_token}, headers=bearer(aanvrager_token)
    )
    return r.status_code


async def _csrf_headers(client: AsyncClient, token: str) -> dict[str, str]:
    csrf = await client.get("/api/v1/auth/csrf-token", headers=bearer(token))
    assert csrf.status_code == 200, f"csrf-token gaf {csrf.status_code}: {csrf.text}"
    return {**bearer(token), "X-CSRF-Token": str(csrf.json()["csrf_token"])}


async def _inloggen_met_refresh(client: AsyncClient, email: str) -> tuple[str, str]:
    """Echt inloggen en BEIDE tokens uit het antwoord halen (de cookies blijven in de client)."""
    r = await client.post("/api/v1/auth/login", data={"username": email, "password": WACHTWOORD})
    assert r.status_code == 200, f"inloggen als {email} gaf {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("refresh_token"), (
        "de proefopstelling klopt niet: login geeft geen refresh_token"
    )
    return str(body["access_token"]), str(body["refresh_token"])


async def _vernieuw(client: AsyncClient, refresh_token: str) -> int:
    client.cookies.clear()
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    return r.status_code


class TestWieMagWelkTokenIntrekken:
    async def test_an_employee_can_revoke_their_own_token(self, client: AsyncClient) -> None:
        beheerder, _ = await _beheerder(client, "eigen")
        _, token = await _medewerker(client, beheerder, "medewerker")

        status = await _trek_in(client, token, token)
        na = await client.get(_INGANG, headers=bearer(token))

        assert status == 200 and na.status_code == 401, (
            f"eigen token intrekken gaf {status}, daarna {na.status_code}"
        )

    async def test_an_employee_cannot_revoke_the_token_of_a_colleague(
        self, client: AsyncClient
    ) -> None:
        beheerder, _ = await _beheerder(client, "collega")
        _, token_a = await _medewerker(client, beheerder, "medewerker-a")
        _, token_b = await _medewerker(client, beheerder, "medewerker-b")

        status = await _trek_in(client, token_a, token_b)
        na = await client.get(_INGANG, headers=bearer(token_b))

        assert status in _GEWEIGERD, (
            f"medewerker A trok het token van collega B in en kreeg {status}; verwacht 403 of 404"
        )
        assert na.status_code == 200, "het token van B is ondanks de weigering toch ingetrokken"

    async def test_an_admin_of_another_tenant_cannot_revoke_the_token(
        self, client: AsyncClient
    ) -> None:
        _, token_a = await _beheerder(client, "tenant-a")
        _, token_b = await _beheerder(client, "tenant-b")

        status = await _trek_in(client, token_b, token_a)
        na = await client.get(_INGANG, headers=bearer(token_a))

        assert status in _GEWEIGERD, (
            f"een beheerder van een ANDERE tenant trok het token in en kreeg {status}"
        )
        assert na.status_code == 200, "het token van de andere tenant is toch ingetrokken"

    async def test_an_admin_can_revoke_the_token_of_an_employee_of_the_same_tenant(
        self, client: AsyncClient
    ) -> None:
        beheerder, token_beheerder = await _beheerder(client, "beheer")
        _, token_medewerker = await _medewerker(client, beheerder, "werknemer")

        status = await _trek_in(client, token_beheerder, token_medewerker)
        na = await client.get(_INGANG, headers=bearer(token_medewerker))

        assert status == 200 and na.status_code == 401, (
            f"beheerder trok het token van een medewerker uit dezelfde tenant in: {status}, "
            f"daarna {na.status_code}"
        )

    async def test_the_blacklist_row_belongs_to_the_holder_and_names_the_revoker(
        self, client: AsyncClient
    ) -> None:
        beheerder, token_beheerder = await _beheerder(client, "rij-beheer")
        medewerker, token_medewerker = await _medewerker(client, beheerder, "rij-medewerker")
        beheerder_id = een_waarde("SELECT id FROM users WHERE email = :e", e=beheerder)
        medewerker_id = een_waarde("SELECT id FROM users WHERE email = :e", e=medewerker)

        assert await _trek_in(client, token_beheerder, token_medewerker) == 200
        gevonden = rijen(
            "SELECT user_id, revoked_by FROM token_blacklist WHERE user_id = :u OR revoked_by = :b",
            u=medewerker_id,
            b=beheerder_id,
        )

        assert gevonden == [(medewerker_id, beheerder_id)], (
            f"blacklistrij(en) (eigenaar, intrekker) = {gevonden}; verwacht "
            f"[({medewerker_id}, {beheerder_id})]"
        )


class TestUitloggenMeldtGeenSuccesBijEenMislukteIntrekking:
    async def test_logout_does_not_report_success_when_the_revocation_fails(
        self, client: AsyncClient
    ) -> None:
        _, token = await _beheerder(client, "faalt")
        headers = await _csrf_headers(client, token)

        with patch(
            "src.core.api.auth.router_token.oauth2_service.revoke_token",
            new=AsyncMock(return_value=False),
        ):
            r = await client.post("/api/v1/auth/logout", headers=headers)

        assert r.status_code >= 500, (
            f"uitloggen terwijl het intrekken mislukt gaf {r.status_code} {r.text}; "
            "de klant denkt dat zijn sessie dicht is terwijl het token nog werkt"
        )

    async def test_logout_does_not_report_success_when_the_revocation_raises(
        self, client: AsyncClient
    ) -> None:
        _, token = await _beheerder(client, "gooit")
        headers = await _csrf_headers(client, token)

        with patch(
            "src.core.api.auth.router_token.oauth2_service.revoke_token",
            new=AsyncMock(side_effect=RuntimeError("database weg")),
        ):
            r = await client.post("/api/v1/auth/logout", headers=headers)

        assert r.status_code >= 500, f"uitloggen met een fout gaf {r.status_code} {r.text}"

    async def test_logout_does_not_report_success_when_only_the_access_token_revocation_fails(
        self, client: AsyncClient
    ) -> None:
        """Geen refresh-cookie: de mislukking zit dan ALLEEN in het intrekken van het access-token."""
        _, token = await _beheerder(client, "alleen-access")
        headers = await _csrf_headers(client, token)
        client.cookies.clear()

        with patch(
            "src.core.api.auth.router_token.oauth2_service.revoke_token",
            new=AsyncMock(return_value=False),
        ):
            r = await client.post("/api/v1/auth/logout", headers=headers)

        assert r.status_code >= 500, (
            f"uitloggen met een mislukte intrekking van het access-token gaf {r.status_code}"
        )

    async def test_logout_does_not_report_success_when_only_the_refresh_token_revocation_fails(
        self, client: AsyncClient
    ) -> None:
        """Alleen het refresh-token faalt. Het router-pad trekt dat EERST in en stopt dan met een 500.

        Het access-token komt in deze test dus niet aan de beurt; dat is de volgorde waar de
        herhaalbaarheid van uitloggen op rust (zie `logout_endpoint`).
        """
        from src.core.api.auth.router_token import oauth2_service
        from src.core.auth.token_kind import TokenKind

        echte_intrekking = oauth2_service.revoke_token

        async def alleen_refresh_faalt(*args: object, **kwargs: object) -> bool:
            if kwargs.get("expected_kind") == TokenKind.REFRESH:
                return False
            # De hulpfunctie zelf is los getypeerd; de echte methode kent de argumenten wel.
            return await echte_intrekking(*args, **kwargs)  # type: ignore[arg-type]  # noqa: E501

        email, _ = await _beheerder(client, "alleen-refresh")
        token, _refresh = await _inloggen_met_refresh(client, email)
        headers = await _csrf_headers(client, token)

        with patch(
            "src.core.api.auth.router_token.oauth2_service.revoke_token",
            new=alleen_refresh_faalt,
        ):
            r = await client.post("/api/v1/auth/logout", headers=headers)

        assert r.status_code >= 500, (
            f"uitloggen met een mislukte intrekking van het refresh-token gaf {r.status_code}"
        )

    async def test_logout_still_reports_success_when_it_works(self, client: AsyncClient) -> None:
        _, token = await _beheerder(client, "werkt")
        headers = await _csrf_headers(client, token)

        r = await client.post("/api/v1/auth/logout", headers=headers)

        assert r.status_code == 200, f"gewoon uitloggen gaf {r.status_code} {r.text}"


class TestHetRefreshTokenWordtBijUitloggenIngetrokken:
    async def test_the_refresh_token_works_before_logout(self, client: AsyncClient) -> None:
        email, _ = await _beheerder(client, "voor")
        _, refresh = await _inloggen_met_refresh(client, email)

        assert await _vernieuw(client, refresh) == 200, (
            "het refresh-token werkt al voor het uitloggen niet; dan bewijst een 401 erna niets"
        )

    async def test_the_refresh_token_in_the_cookie_is_refused_after_logout(
        self, client: AsyncClient
    ) -> None:
        """Zoals een browser: het refresh-token zit alleen in de cookie, niemand stuurt het mee."""
        email, _ = await _beheerder(client, "cookie")
        token, refresh = await _inloggen_met_refresh(client, email)
        headers = await _csrf_headers(client, token)

        r = await client.post("/api/v1/auth/logout", headers=headers)
        assert r.status_code == 200, f"uitloggen gaf {r.status_code} {r.text}"

        assert await _vernieuw(client, refresh) == 401, (
            "na uitloggen geeft het gekopieerde refresh-token nog een nieuw access-token"
        )

    async def test_the_refresh_token_sent_in_the_body_is_refused_after_logout(
        self, client: AsyncClient
    ) -> None:
        """Zoals een API-client zonder cookies: het refresh-token gaat in het verzoek mee."""
        email, _ = await _beheerder(client, "body")
        token, refresh = await _inloggen_met_refresh(client, email)
        headers = await _csrf_headers(client, token)
        client.cookies.clear()

        r = await client.post(
            "/api/v1/auth/logout", headers=headers, json={"refresh_token": refresh}
        )
        assert r.status_code == 200, f"uitloggen gaf {r.status_code} {r.text}"

        assert await _vernieuw(client, refresh) == 401, (
            "na uitloggen met het refresh-token in het verzoek werkt dat token nog"
        )

    async def test_a_refresh_token_of_another_user_is_not_revoked_by_my_logout(
        self, client: AsyncClient
    ) -> None:
        email_a, _ = await _beheerder(client, "mijn")
        email_b, _ = await _beheerder(client, "ander")
        token_a, _refresh_a = await _inloggen_met_refresh(client, email_a)
        _token_b, refresh_b = await _inloggen_met_refresh(client, email_b)
        headers = await _csrf_headers(client, token_a)
        client.cookies.clear()

        await client.post("/api/v1/auth/logout", headers=headers, json={"refresh_token": refresh_b})

        assert await _vernieuw(client, refresh_b) == 200, (
            "uitloggen als A trok het refresh-token van B in"
        )

    async def test_a_second_refresh_token_of_the_same_user_keeps_working(
        self, client: AsyncClient
    ) -> None:
        email, _ = await _beheerder(client, "tweede")
        token_1, refresh_1 = await _inloggen_met_refresh(client, email)
        _token_2, refresh_2 = await _inloggen_met_refresh(client, email)
        headers = await _csrf_headers(client, token_1)
        client.cookies.clear()

        await client.post("/api/v1/auth/logout", headers=headers, json={"refresh_token": refresh_1})

        assert await _vernieuw(client, refresh_2) == 200, (
            "uitloggen op het ene apparaat trok het refresh-token van het andere apparaat in"
        )
