"""Na uitloggen is het token onbruikbaar -- gemeten over de echte voordeur (meetlat eis 3).

**Waarom deze test er is.** `tests/unit/api/auth/test_op188_token_stays_valid_after_logout.py`
roept `logout_endpoint()` rechtstreeks aan met een nagemaakte database en controleert daarna
een TWEEDE, nagemaakte database. Die twee delen niets: hij bewijst dat beide helften los
bestaan, niet dat een uitgelogd token wordt geweigerd.
`tests/integration/test_auth_cookie_session.py::test_cookie_auth_fails_after_logout` heeft
een ander gat: uitloggen wist de cookie uit de client, dus de 401 daarna komt doordat de client
niets meer STUURT, en het token wordt nooit opnieuw aangeboden. Wat de klant of een aanvaller
met een gekopieerd token doet, is HETZELFDE token opnieuw sturen. Dat doet deze test.

**Wat hier wel gebeurt.** De echte app (`create_test_app()`), een echte registratie en
inlog, een echt CSRF-token uit Redis, een echte uitlog en daarna HETZELFDE token opnieuw als
Bearer-token op een beschermd eindpunt. De blacklistrij wordt met een aparte
databaseverbinding teruggelezen.

**Vier richtingen, met opzet.** Zonder de tegenrichtingen is "weiger elk token" of "trek alle
tokens van deze gebruiker in" een geldige oplossing:
- voor het uitloggen werkt het token (anders bewijst de 401 daarna niets);
- na het uitloggen wordt precies dat token geweigerd, op twee verschillende ingangen;
- een TWEEDE token van dezelfde gebruiker (tweede apparaat) blijft werken;
- een token van een andere gebruiker blijft werken.

**Wat deze test NIET zegt.** De test-PostgreSQL verbindt als `postgres` en omzeilt Row Level
Security; hier wordt de intrekking bewezen, niet de tenantscheiding in de database.

**Draaien** (Redis van de integratieomgeving is nodig voor het CSRF-token):
    REDIS_URL=redis://127.0.0.1:6380 pytest tests/integration/security/test_een_uitgelogd_token_wordt_geweigerd.py

**Mutatiebewijs, gemeten 2026-10-12** (de methode is tijdens de run vervangen via een
pytest-plugin; er is geen productiebestand aangeraakt). Normaal: 6 geslaagd.
- `revoke_token` doet niets maar meldt succes -> ROOD: `refused_after_logout`,
  `refused_after_logout_on_the_second_entrance`, `blacklist_row_exists_after_logout` (3 rood).
- `is_jti_revoked` geeft altijd False -> ROOD: de twee `refused_after_logout`-tests (2 rood).
- `is_jti_revoked` geeft altijd True -> ROOD: alle 6, ook `token_works_before_logout`.
- `is_jti_revoked` kijkt of er IETS op de blacklist staat in plaats van naar de jti -> ROOD:
  `second_token_of_the_same_user_keeps_working`, `token_of_another_user_keeps_working` en de
  tweede ingang. NIET rood: `refused_after_logout` op `/auth/me`; die test alleen kan dus
  een te grove intrekking niet vangen, daarom bestaan de twee tegenrichtingen.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.security._voordeur_hulp import (  # noqa: F401  (fixtures)
    bearer,
    client,
    een_waarde,
    limiters_leeg,
    log_in,
    registreer,
    unieke_email,
)

pytestmark = [pytest.mark.integration, pytest.mark.security]

#: Twee verschillende ingangen: `get_current_user` (via /auth/me) en een route die via de
#: tenant- en rechtencontrole loopt (/api/rbac/roles). Dezelfde ingangen als
#: `tests/unit/auth/test_een_ingetrokken_token_komt_er_niet_in.py`, nu zonder testdubbels.
_INGANG_EEN = "/api/v1/auth/me"
_INGANG_TWEE = "/api/rbac/roles"


async def _nieuwe_gebruiker(client: AsyncClient, voorvoegsel: str) -> tuple[str, str]:
    email = unieke_email(voorvoegsel)
    r = await registreer(client, email)
    assert r.status_code == 201, f"registreren gaf {r.status_code}: {r.text}"
    return email, await log_in(client, email)


async def _log_uit(client: AsyncClient, token: str) -> None:
    """Uitloggen zoals de frontend: eerst een CSRF-token ophalen, dan POST /auth/logout."""
    csrf = await client.get("/api/v1/auth/csrf-token", headers=bearer(token))
    assert csrf.status_code == 200, f"csrf-token gaf {csrf.status_code}: {csrf.text}"
    r = await client.post(
        "/api/v1/auth/logout",
        headers={**bearer(token), "X-CSRF-Token": str(csrf.json()["csrf_token"])},
    )
    assert r.status_code == 200, f"uitloggen gaf {r.status_code}: {r.text}"


async def test_the_token_works_before_logout(client: AsyncClient) -> None:
    _, token = await _nieuwe_gebruiker(client, "voor")
    r = await client.get(_INGANG_EEN, headers=bearer(token))
    assert r.status_code == 200, (
        f"Het token werkt al voor het uitloggen niet ({r.status_code}). Dan bewijst een 401 "
        "na het uitloggen niets."
    )


async def test_the_same_token_is_refused_after_logout(client: AsyncClient) -> None:
    _, token = await _nieuwe_gebruiker(client, "na")
    await _log_uit(client, token)
    r = await client.get(_INGANG_EEN, headers=bearer(token))
    assert r.status_code == 401, (
        f"Na uitloggen gaf hetzelfde token op {_INGANG_EEN} status {r.status_code}. "
        "Uitloggen maakt het token dan niet ongeldig (meetlat eis 3, ADR-036 OP-188)."
    )


async def test_the_same_token_is_refused_after_logout_on_the_second_entrance(
    client: AsyncClient,
) -> None:
    _, token = await _nieuwe_gebruiker(client, "twee")
    voor = await client.get(_INGANG_TWEE, headers=bearer(token))
    assert voor.status_code == 200, (
        f"{_INGANG_TWEE} geeft voor het uitloggen al {voor.status_code}; kies een ingang die "
        "voor een admin werkt, anders is de weigering na afloop niet te onderscheiden."
    )
    await _log_uit(client, token)
    na = await client.get(_INGANG_TWEE, headers=bearer(token))
    assert na.status_code == 401, (
        f"Na uitloggen gaf hetzelfde token op {_INGANG_TWEE} status {na.status_code}."
    )


async def test_the_blacklist_row_exists_after_logout(client: AsyncClient) -> None:
    email, token = await _nieuwe_gebruiker(client, "rij")
    user_id = een_waarde("SELECT id FROM users WHERE email = :e", e=email)
    voor = een_waarde("SELECT count(*) FROM token_blacklist WHERE user_id = :u", u=user_id)
    assert voor == 0, "de proefopstelling klopt niet: er stond al een ingetrokken token"
    await _log_uit(client, token)
    na = een_waarde(
        "SELECT count(*) FROM token_blacklist WHERE user_id = :u AND reason = 'logout'",
        u=user_id,
    )
    # Twee: het access-token en het refresh-token uit de cookie van dezelfde sessie. Tot
    # 2026-10-14 was dit 1; uitloggen trekt het refresh-token nu ook in (beveiligingsnazorg,
    # `tests/integration/test_beveiligingsnazorg_tokens.py`).
    assert na == 2, (
        f"Na uitloggen staan er {na} blacklistrijen met reden 'logout' voor deze gebruiker, "
        "verwacht precies 2 (access- en refresh-token)."
    )


async def test_a_second_token_of_the_same_user_keeps_working(client: AsyncClient) -> None:
    email, eerste = await _nieuwe_gebruiker(client, "apparaten")
    tweede = await log_in(client, email)
    assert tweede != eerste, "de proefopstelling klopt niet: twee logins gaven hetzelfde token"
    await _log_uit(client, eerste)
    r = await client.get(_INGANG_EEN, headers=bearer(tweede))
    assert r.status_code == 200, (
        f"Het tweede token van dezelfde gebruiker werd na uitloggen van het eerste geweigerd "
        f"({r.status_code}). Intrekken gebeurt dan op gebruiker in plaats van op token."
    )


async def test_a_token_of_another_user_keeps_working(client: AsyncClient) -> None:
    _, token_a = await _nieuwe_gebruiker(client, "gebruiker-a")
    _, token_b = await _nieuwe_gebruiker(client, "gebruiker-b")
    await _log_uit(client, token_a)
    r = await client.get(_INGANG_EEN, headers=bearer(token_b))
    assert r.status_code == 200, (
        f"Het token van een andere gebruiker werd geweigerd ({r.status_code}) nadat A uitlogde."
    )
