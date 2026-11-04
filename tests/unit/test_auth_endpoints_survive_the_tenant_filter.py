"""De publieke auth-endpoints moeten werken met de tenantfilter aan (ADR-036 OP-131).

**De bevinding.** `app_lifespan._init_tenant_filtering` registreert bij ELKE start een globale
`do_orm_execute`-listener op de `Session`-klasse. Die is fail-secure: is er geen tenant in de
ContextVar, dan plakt hij `WHERE false` aan iedere SELECT. En `/api/v1/auth` staat in
`EXCLUDED_PREFIXES` van de tenant-middleware, dus daar is per definitie geen tenantcontext.

Gevolg in productie: `forgot-password`, `reset-password`, `change-password`, `validate` en
`verify-token` vinden NOOIT een gebruiker. Stil, want `forgot_password` geeft met opzet altijd 200
terug om e-mail-aftasten te voorkomen, en de `except Exception` eronder geeft datzelfde antwoord.

`router_login.py` en `router_registration.py` hebben dit wel goed: die wikkelen hun lookup in
`TenantFilterBypass()` met de reden erbij ("we don't have tenant context yet"). `router_password.py`
(3 queries) en `router_token.py` (2) doen dat niet.

**Waarom geen enkele bestaande test dit ving.** Ze draaien met de listener NIET geinstalleerd -- een
toestand die in productie nooit voorkomt. Alleen als een eerder testbestand in dezelfde xdist-worker
`init_tenant_auto_filtering()` had aangeroepen, viel er iets om; dat las als flakiness (OP-20).

**Waarom de fixture de listener weer opruimt.** Zonder opruimen vervuilt deze test elke latere
ORM-test in dezelfde worker -- precies het probleem uit OP-20. Dat is mogelijk sinds
`init_tenant_auto_filtering()` de listener teruggeeft.

**Mutatietest (2026-08-11, beide richtingen):**

1. De `TenantFilterBypass` uit `router_password.py:100` halen -> ROOD (geen mail). Idem voor de
   lookup in `router_token.py` -> ROOD (401 op een geldig token).
2. De andere kant: een ONBEKEND e-mailadres stuurt nog steeds niets
   (`test_an_unknown_email_still_sends_nothing`). Zonder die helft zou "stuur altijd een mail" een
   geldige oplossing zijn, en dan is de e-mail-aftastbescherming weg.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session


@pytest.fixture
def tenantfilter_live() -> Iterator[None]:
    """Zet de wereld neer zoals productie hem heeft: filter aan, geen tenantcontext.

    De autouse-fixture `_reset_global_state` in `tests/conftest.py` zet `_tenant_context` op None
    voor en na elke test, dus de tweede helft van die voorwaarde staat er al.
    """
    from src.core.database.tenant_query_filter import init_tenant_auto_filtering

    listener = init_tenant_auto_filtering()
    try:
        yield
    finally:
        event.remove(Session, "do_orm_execute", listener)


@pytest.mark.asyncio
class TestForgotPasswordWithTheFilterLive:
    async def test_the_reset_mail_is_actually_sent(self, test_client, test_user, tenantfilter_live):
        """De kern: zonder bypass vindt het endpoint de gebruiker niet en gaat er niets uit."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(return_value=True)
        with (
            patch(
                "src.core.api.auth.router_password.get_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch("src.core.api.auth.router_password.send_password_reset_email") as mock_send,
        ):
            response = await test_client.post(
                "/api/v1/auth/forgot-password",
                json={"email": test_user["email"]},
            )

            assert response.status_code == 200
            assert mock_send.call_count == 1, (
                "Er gaat geen herstelmail uit terwijl de gebruiker bestaat. Het endpoint geeft wel "
                "200 (dat doet het altijd, tegen e-mail-aftasten), dus dit faalt in productie "
                "volledig stil. Oorzaak: de query mist `TenantFilterBypass` en krijgt van de "
                "fail-secure tenantfilter een `WHERE false` mee."
            )

    async def test_an_unknown_email_still_sends_nothing(self, test_client, tenantfilter_live):
        """De andere richting -- anders zou 'stuur altijd een mail' een geldige oplossing zijn."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(return_value=True)
        with (
            patch(
                "src.core.api.auth.router_password.get_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch("src.core.api.auth.router_password.send_password_reset_email") as mock_send,
        ):
            response = await test_client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "bestaat-niet-9f2a@example.com"},
            )

            assert response.status_code == 200
            assert mock_send.call_count == 0, (
                "Er gaat een herstelmail naar een adres dat geen account heeft."
            )


@pytest.mark.asyncio
class TestAccountLockoutWithTheFilterLive:
    """De brute-force-beveiliging telde niet op zolang de filter aanstond.

    Gevonden door `tests/architecture/test_auth_router_queries_bypass_the_tenant_filter.py`, niet
    door mij: die guard wees twee queries in `router_login.py` aan die ik zelf had overgeslagen.

    Het login-pad zoekt het bestaande `AccountLockout`-record. Vindt het er geen, dan maakt het een
    NIEUWE rij met `failed_attempts=0` en hoogt die naar 1 op. Er is geen unique constraint op
    `user_id`, dus zonder bypass levert elke mislukte poging een verse rij op en komt de teller
    nooit boven 1: het account gaat nooit op slot, zonder foutmelding of logregel.

    **Let op welke query dat is.** De helper `get_or_create_lockout_record` doet hetzelfde, maar het
    login-endpoint gebruikt hem NIET -- daar staat een eigen, inline query (`router_login.py:196`).
    Gemeten: de bypass uit de helper halen laat deze test GROEN; uit de inline query halen maakt hem
    rood met vijf records en tellers [1, 1, 1, 1, 1]. De helper wordt alleen door `router.py`
    geherexporteerd. Wie hier muteert om de test te toetsen, moet dus de inline query hebben.

    **Waarom dit de DATABASE toetst en niet de statuscode.** Het login-endpoint heeft ook een rate
    limiter. Een 429 op poging zes kan dus van de limiter komen in plaats van de lockout, en dan
    slaagt de test terwijl de beveiliging stuk is. Het aantal RIJEN is niet voor tweeerlei uitleg
    vatbaar.
    """

    async def test_failed_attempts_accumulate_on_one_record(
        self, test_client, test_user, db_session, tenantfilter_live
    ):
        """Vijf mislukte pogingen horen EEN record met teller 5 op te leveren, geen vijf records."""
        from sqlalchemy import select

        from src.core.auth.models.account_lockout import AccountLockout
        from src.core.database.tenant_query_filter import TenantFilterBypass

        for _ in range(5):
            await test_client.post(
                "/api/v1/auth/login",
                data={"username": test_user["email"], "password": "fout-wachtwoord-123"},
            )

        with TenantFilterBypass():
            rijen = (
                (
                    await db_session.execute(
                        select(AccountLockout).where(AccountLockout.user_id == test_user["id"])
                    )
                )
                .scalars()
                .all()
            )

        assert len(rijen) == 1, (
            f"Er staan {len(rijen)} lockout-records voor deze gebruiker in plaats van 1. Elke "
            f"mislukte poging maakt een verse rij omdat de bestaande niet gevonden wordt, dus de "
            f"teller komt nooit boven 1 en het account gaat nooit op slot. Tellers: "
            f"{[r.failed_attempts for r in rijen]}"
        )
        assert rijen[0].failed_attempts >= 5, (
            f"De teller staat op {rijen[0].failed_attempts} na vijf mislukte pogingen."
        )


@pytest.mark.asyncio
class TestVerifyTokenWithTheFilterLive:
    async def test_a_valid_token_still_resolves_to_its_user(
        self, test_client, test_user, test_token, tenantfilter_live
    ):
        """`router_token.py:317` doet dezelfde lookup zonder bypass.

        Het id komt hier uit een GEVERIFIEERDE JWT, niet uit invoer -- de bypass opent dus geen
        deur die de token-verificatie zelf niet al heeft geopend.
        """
        response = await test_client.post(
            "/api/v1/auth/verify-token",
            json={"token": test_token},
        )

        assert response.status_code == 200, (
            f"Een geldig token wordt niet meer herkend (status {response.status_code}). De lookup "
            f"van de gebruiker loopt op de fail-secure tenantfilter stuk. Antwoord: {response.text}"
        )
