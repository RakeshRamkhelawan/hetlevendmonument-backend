"""Een nieuwe medewerker kan zelf inloggen: de mail gaat echt, en stapfouten lekken niet (2026-10-15).

Brief: docs/agent-briefs/generated/2026-10-15-sprint-dag-nieuwe-medewerker-kan-inloggen.md.

Gemeten bij de acceptant (scenario 16, bijvangst scenario 9): een beheerder voegt een medewerker toe,
de gebruiker staat op "Actief", maar de mailbox bleef leeg, ook na "Wachtwoord vergeten". Oorzaken,
gemeten op 2026-10-15 tegen de draaiende backend (een hostproces, `uvicorn src.main:app`):

1. `get_email_service()` koos de console-variant (die niets verstuurt en `True` geeft) omdat
   `SMTP_HOST` niet in `os.environ` stond. Die variant is nu alleen toegestaan als `TESTING=1`;
   anders is er een zichtbare fout (log ERROR en `False`).
2. De Mailpit-container publiceerde alleen poort 8025, niet SMTP op 1025 (docker-compose.dev.yml).
3. De route die de beheerder gebruikt (`POST /api/v1/users/`, `users_list_router.create_user`;
   `user_management/crud_router.py` wordt NIET gemount) eiste een wachtwoord van de beheerder.

Wat gemeten wordt (alles over de echte app en echte Postgres; de SMTP-aflevering is op de grens
vervangen door `tests/unit/debiteuren/_smtp_dubbel.py`, de rest van de keten loopt echt):

(a) zonder mailinstelling en buiten tests is versturen een fout, geen stille `True`;
(b) een beheerder nodigt een medewerker uit zonder wachtwoord: er gaat een mail met een link; met die
    link kiest de medewerker een wachtwoord en logt in;
(c) een mislukte mail is zichtbaar voor de beheerder en in het log;
(d) een mislukte pakketstap geeft geen uitzonderingstekst in `steps[].error`.

Wat NIET gemeten is: een echte aflevering in Mailpit door de draaiende backend (die moet door de regie
met een herstart worden gemeten, nadat Mailpit poort 1025 publiceert en `SMTP_HOST`/`SMTP_PORT` in de
omgeving van de backend staan).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient

from src.core.services.email import (
    ConsoleEmailService,
    EmailMessage,
    EmailServiceInterface,
    SMTPEmailService,
    get_email_service,
)
from tests.integration.security._voordeur_hulp import (  # noqa: F401
    WACHTWOORD,
    bearer,
    client,
    limiters_leeg,
    log_in,
    registreer,
    unieke_email,
)
from tests.unit.debiteuren._smtp_dubbel import (
    SmtpDubbel,
    installeer_smtp_dubbel,
    zet_testmailbox,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

NIEUW_WACHTWOORD = "EigenGekozenWachtwoord9"  # nosec B105 - testwaarde


@pytest.fixture(autouse=True)
def _verse_redis_verbinding() -> Iterator[None]:
    """Elke test een eigen Redis-verbinding: een pool uit de vorige test hangt aan een gesloten loop.

    Gemeten: zonder dit gaf `GET /auth/csrf-token` in een latere test een 500 ("Failed to generate
    CSRF token"), terwijl dezelfde test los slaagde.
    """
    from src.core.database.redis import reset_redis_pool

    reset_redis_pool()
    yield
    reset_redis_pool()


# ---------------------------------------------------------------------------
# (a) zonder mailinstelling buiten tests: een zichtbare fout, geen stille namaak
# ---------------------------------------------------------------------------


def _geen_mailinstelling(monkeypatch: pytest.MonkeyPatch, *, testing: str | None) -> None:
    """Een omgeving zoals een lokaal draaiend hostproces zonder SMTP-instelling."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    if testing is None:
        monkeypatch.delenv("TESTING", raising=False)
    else:
        monkeypatch.setenv("TESTING", testing)
    # De app-configuratie leest `.env` van de machine van wie de test draait; hier gaat het om de
    # keuze zonder instelling, dus de configuratie levert niets.
    from src.core.services import email as email_module

    monkeypatch.setattr(email_module, "_smtp_uit_configuratie", lambda: (None, None), raising=False)


@pytest.mark.integration
class TestZonderMailinstelling:
    def test_buiten_tests_is_de_dienst_niet_de_console(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _geen_mailinstelling(monkeypatch, testing=None)

        assert not isinstance(get_email_service(), ConsoleEmailService)

    async def test_buiten_tests_geeft_versturen_een_fout_en_geen_stille_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _geen_mailinstelling(monkeypatch, testing=None)

        gelukt = await get_email_service().send(
            EmailMessage(to="iemand@klant.example", subject="Onderwerp", body="Tekst")
        )

        assert gelukt is False

    async def test_buiten_tests_staat_de_fout_in_het_log(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _geen_mailinstelling(monkeypatch, testing=None)

        with caplog.at_level(logging.ERROR):
            await get_email_service().send(
                EmailMessage(to="iemand@klant.example", subject="Onderwerp", body="Tekst")
            )

        assert any(
            r.levelno >= logging.ERROR and "email_not_configured" in r.getMessage()
            for r in caplog.records
        ), [r.getMessage() for r in caplog.records]

    def test_in_tests_blijft_de_console_toegestaan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _geen_mailinstelling(monkeypatch, testing="1")

        assert isinstance(get_email_service(), ConsoleEmailService)

    def test_met_smtp_host_is_het_smtp_ook_buiten_tests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _geen_mailinstelling(monkeypatch, testing=None)
        monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
        monkeypatch.setenv("SMTP_PORT", "1025")

        dienst = get_email_service()

        assert isinstance(dienst, SMTPEmailService) and (dienst.host, dienst.port) == (
            "127.0.0.1",
            1025,
        )

    def test_de_instelling_komt_ook_uit_de_app_configuratie(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dezelfde bron als de rest van de configuratie: `.env` komt niet vanzelf in os.environ."""
        _geen_mailinstelling(monkeypatch, testing=None)
        from src.core.services import email as email_module

        monkeypatch.setattr(
            email_module, "_smtp_uit_configuratie", lambda: ("127.0.0.1", 1025), raising=False
        )

        dienst = get_email_service()

        assert isinstance(dienst, SMTPEmailService) and (dienst.host, dienst.port) == (
            "127.0.0.1",
            1025,
        )

    async def test_zonder_afzender_gebruikt_smtp_het_standaardadres_van_het_product(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mailpit heeft geen inlog; een lege `From` wordt geweigerd."""
        zet_testmailbox(monkeypatch)
        monkeypatch.delenv("EMAIL_FROM")
        dubbel = installeer_smtp_dubbel(monkeypatch)

        await SMTPEmailService().send(
            EmailMessage(to="iemand@klant.example", subject="Onderwerp", body="Tekst")
        )

        assert dubbel.ontvangen[0].afzender == "noreply@sanskritisetu.org"


# ---------------------------------------------------------------------------
# (b) en (c): een beheerder nodigt uit, de medewerker kiest zelf een wachtwoord
# ---------------------------------------------------------------------------


async def _beheerder(client: AsyncClient) -> tuple[dict[str, str], int]:
    """Een nieuwe klant met zijn beheerder (zelfregistratie), echt ingelogd."""
    email = unieke_email("beheer")
    aangemeld = await registreer(client, email)
    assert aangemeld.status_code in (200, 201), aangemeld.text
    kop = bearer(await log_in(client, email))
    ik = await client.get("/api/v1/auth/me", headers=kop)
    assert ik.status_code == 200, ik.text
    # Zoals de frontend: eerst een echt CSRF-token (uit Redis) ophalen en bij elk schrijfverzoek meesturen.
    csrf = await client.get("/api/v1/auth/csrf-token", headers=kop)
    assert csrf.status_code == 200, f"csrf-token gaf {csrf.status_code}: {csrf.text}"
    return {**kop, "X-CSRF-Token": str(csrf.json()["csrf_token"])}, int(ik.json()["tenant_id"])


def _link_uit(dubbel: SmtpDubbel) -> str:
    assert dubbel.ontvangen, "er is geen mail verstuurd"
    gevonden = re.search(
        r"https?://\S+/reset-password\?token=[\w\-]+", dubbel.ontvangen[0].alle_delen
    )
    assert gevonden, dubbel.ontvangen[0].alle_delen[:400]
    return gevonden.group(0)


@pytest.mark.integration
class TestUitnodigen:
    async def test_een_beheerder_nodigt_uit_zonder_wachtwoord_en_er_gaat_een_mail_met_een_link(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        kop, tenant = await _beheerder(client)
        medewerker = unieke_email("nieuw")

        antwoord = await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": medewerker},
            headers=kop,
        )

        assert antwoord.status_code == 201, antwoord.text
        assert antwoord.json()["invitation_email_sent"] is True
        assert [m.ontvanger for m in dubbel.ontvangen] == [medewerker]
        _link_uit(dubbel)

    async def test_met_de_link_kiest_de_medewerker_een_wachtwoord_en_logt_in(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        kop, tenant = await _beheerder(client)
        medewerker = unieke_email("nieuw")
        await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": medewerker},
            headers=kop,
        )
        token = _link_uit(dubbel).split("token=")[1]

        gekozen = await client.post(
            "/api/v1/auth/reset-password", json={"token": token, "new_password": NIEUW_WACHTWOORD}
        )
        ingelogd = await client.post(
            "/api/v1/auth/login", data={"username": medewerker, "password": NIEUW_WACHTWOORD}
        )

        assert gekozen.status_code == 200, gekozen.text
        assert ingelogd.status_code == 200, ingelogd.text
        assert ingelogd.json()["access_token"]

    async def test_de_link_werkt_maar_een_keer(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        kop, tenant = await _beheerder(client)
        await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": unieke_email("nieuw")},
            headers=kop,
        )
        token = _link_uit(dubbel).split("token=")[1]
        await client.post(
            "/api/v1/auth/reset-password", json={"token": token, "new_password": NIEUW_WACHTWOORD}
        )

        tweede = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "NogEenWachtwoord8"},
        )

        assert tweede.status_code == 400, tweede.text

    async def test_zonder_link_is_de_nieuwe_gebruiker_niet_in_te_loggen(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Het startwachtwoord is willekeurig en onbekend: niemand kan er mee inloggen."""
        zet_testmailbox(monkeypatch)
        installeer_smtp_dubbel(monkeypatch)
        kop, tenant = await _beheerder(client)
        medewerker = unieke_email("nieuw")
        await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": medewerker},
            headers=kop,
        )

        for poging in (WACHTWOORD, "", "password", "Welkom01"):
            ingelogd = await client.post(
                "/api/v1/auth/login", data={"username": medewerker, "password": poging}
            )
            assert ingelogd.status_code in (400, 401, 422), (poging, ingelogd.text)

    async def test_de_mail_noemt_geen_wachtwoord_en_is_nederlands(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        kop, tenant = await _beheerder(client)
        await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": unieke_email("nieuw")},
            headers=kop,
        )

        tekst = dubbel.ontvangen[0].alle_delen

        assert "uitgenodigd" in tekst and "wachtwoord" in tekst.lower()
        assert "Password" not in tekst and "Click" not in tekst

    async def test_het_oude_veld_wachtwoord_blijft_werken_en_stuurt_geen_mail(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        kop, tenant = await _beheerder(client)
        medewerker = unieke_email("oud")

        antwoord = await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": medewerker, "password": WACHTWOORD},
            headers=kop,
        )
        ingelogd = await client.post(
            "/api/v1/auth/login", data={"username": medewerker, "password": WACHTWOORD}
        )

        assert antwoord.status_code == 201, antwoord.text
        assert antwoord.json().get("invitation_email_sent") in (None, False)
        assert dubbel.ontvangen == []
        assert ingelogd.status_code == 200, ingelogd.text

    async def test_een_bestaand_adres_geeft_geen_mail_en_geen_token(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        kop, tenant = await _beheerder(client)
        medewerker = unieke_email("dubbel")
        await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": medewerker},
            headers=kop,
        )
        eerder = len(dubbel.ontvangen)

        tweede = await client.post(
            "/api/v1/users/",
            params={"target_tenant_id": tenant},
            json={"email": medewerker},
            headers=kop,
        )

        assert tweede.status_code == 400, tweede.text
        assert len(dubbel.ontvangen) == eerder


@pytest.mark.integration
class TestEenMislukteMail:
    async def test_de_beheerder_ziet_dat_de_mail_niet_is_verstuurd_en_het_log_noemt_het(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Geen mailinstelling buiten tests: de dienst meldt een fout en geeft False.
        kop, tenant = await _beheerder(client)
        _geen_mailinstelling(monkeypatch, testing=None)

        with caplog.at_level(logging.ERROR):
            antwoord = await client.post(
                "/api/v1/users/",
                params={"target_tenant_id": tenant},
                json={"email": unieke_email("nieuw")},
                headers=kop,
            )

        assert antwoord.status_code == 201, antwoord.text
        assert antwoord.json()["invitation_email_sent"] is False
        assert any("email_not_configured" in r.getMessage() for r in caplog.records)

    async def test_wachtwoord_vergeten_zonder_mailinstelling_geeft_een_fout_in_het_log(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Het antwoord blijft neutraal (geen enumeratie), maar het mislukken is niet meer stil."""
        import asyncio

        email = unieke_email("vergeten")
        assert (await registreer(client, email)).status_code in (200, 201)
        _geen_mailinstelling(monkeypatch, testing=None)

        with caplog.at_level(logging.ERROR):
            antwoord = await client.post("/api/v1/auth/forgot-password", json={"email": email})
            await asyncio.sleep(0.5)

        assert antwoord.status_code == 200
        assert any("email_not_configured" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# (d) een mislukte pakketstap lekt geen uitzonderingstekst
# ---------------------------------------------------------------------------

GEHEIM_DETAIL = "psycopg2.OperationalError: connection refused at /srv/app/db.py line 88"


@pytest.mark.integration
class TestStapfoutLekt:
    @pytest.fixture
    def stap_faalt_met_uitzondering(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """De skill werpt een uitzondering met interne tekst; `_execute_step` vangt die echt."""
        from src.core.als.agents.loader import EnterpriseCatalogLoader

        def _stuk(self: Any, agent_key: str, tenant_id: int) -> Any:
            raise RuntimeError(GEHEIM_DETAIL)

        monkeypatch.setattr(EnterpriseCatalogLoader, "get_agent_instance", _stuk)

    async def test_een_mislukte_stap_geeft_een_vaste_nederlandse_tekst(
        self, client: AsyncClient, stap_faalt_met_uitzondering: None
    ) -> None:
        # Een beheerder mag het pakket aanzetten en uitvoeren (admin heeft `*:*`).
        kop, _tenant = await _beheerder(client)
        await client.put(
            "/api/v1/packs/activations/hr.reskilling_engine", json={"is_enabled": True}, headers=kop
        )

        antwoord = await client.post(
            "/api/v1/agentic/packs/execute",
            json={"pack_id": "hr.reskilling_engine", "input_data": {}},
            headers=kop,
        )

        assert antwoord.status_code == 200, antwoord.text
        fouten = [s["error"] for s in antwoord.json()["steps"] if s["status"] == "failed"]
        assert fouten, antwoord.text
        assert all(f == "De stap kon niet worden uitgevoerd." for f in fouten), fouten

    async def test_de_uitzonderingstekst_staat_nergens_in_het_antwoord(
        self, client: AsyncClient, stap_faalt_met_uitzondering: None
    ) -> None:
        kop, _tenant = await _beheerder(client)
        await client.put(
            "/api/v1/packs/activations/hr.reskilling_engine", json={"is_enabled": True}, headers=kop
        )

        antwoord = await client.post(
            "/api/v1/agentic/packs/execute",
            json={"pack_id": "hr.reskilling_engine", "input_data": {}},
            headers=kop,
        )

        assert "psycopg2" not in antwoord.text and "/srv/app" not in antwoord.text


# ---------------------------------------------------------------------------
# Het HOOFDPAD: wat de pagina Gebruikersbeheer aanroept (POST /api/v1/admin/create_user)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUitnodigenViaDeBeheerroute:
    """De UI roept `/api/v1/admin/create_user` aan (niet `/api/v1/users/`), met een rol en tot nu toe een
    in de browser verzonnen wachtwoord. Zonder wachtwoord wordt de medewerker uitgenodigd."""

    URL = "/api/v1/admin/create_user"

    async def test_zonder_wachtwoord_gaat_er_een_mail_met_een_link_naar_de_medewerker(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        kop, _tenant = await _beheerder(client)
        medewerker = unieke_email("nieuw")

        antwoord = await client.post(
            self.URL, json={"email": medewerker, "role": "user"}, headers=kop
        )

        assert antwoord.status_code == 201, antwoord.text
        assert antwoord.json()["invitation_email_sent"] is True
        assert [m.ontvanger for m in dubbel.ontvangen] == [medewerker]
        _link_uit(dubbel)

    async def test_met_de_link_kiest_de_medewerker_een_wachtwoord_en_logt_in(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        kop, _tenant = await _beheerder(client)
        medewerker = unieke_email("nieuw")
        await client.post(self.URL, json={"email": medewerker, "role": "user"}, headers=kop)
        token = _link_uit(dubbel).split("token=")[1]

        gekozen = await client.post(
            "/api/v1/auth/reset-password", json={"token": token, "new_password": NIEUW_WACHTWOORD}
        )
        ingelogd = await client.post(
            "/api/v1/auth/login", data={"username": medewerker, "password": NIEUW_WACHTWOORD}
        )

        assert gekozen.status_code == 200, gekozen.text
        assert ingelogd.status_code == 200, ingelogd.text

    async def test_de_gekozen_rol_wordt_nog_steeds_toegekend(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        installeer_smtp_dubbel(monkeypatch)
        kop, _tenant = await _beheerder(client)
        medewerker = unieke_email("rol")

        antwoord = await client.post(
            self.URL, json={"email": medewerker, "role": "user"}, headers=kop
        )

        assert antwoord.status_code == 201, antwoord.text
        assert antwoord.json()["role"] == "user"

    async def test_het_oude_veld_wachtwoord_blijft_werken_en_stuurt_geen_mail(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        kop, _tenant = await _beheerder(client)
        medewerker = unieke_email("oud")

        antwoord = await client.post(
            self.URL,
            json={"email": medewerker, "role": "user", "password": WACHTWOORD},
            headers=kop,
        )
        ingelogd = await client.post(
            "/api/v1/auth/login", data={"username": medewerker, "password": WACHTWOORD}
        )

        assert antwoord.status_code == 201, antwoord.text
        assert antwoord.json()["invitation_email_sent"] is None
        assert dubbel.ontvangen == []
        assert ingelogd.status_code == 200, ingelogd.text

    async def test_een_mislukte_mail_is_zichtbaar_voor_de_beheerder_en_in_het_log(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        kop, _tenant = await _beheerder(client)
        _geen_mailinstelling(monkeypatch, testing=None)

        with caplog.at_level(logging.ERROR):
            antwoord = await client.post(
                self.URL, json={"email": unieke_email("nieuw"), "role": "user"}, headers=kop
            )

        assert antwoord.status_code == 201, antwoord.text
        assert antwoord.json()["invitation_email_sent"] is False
        assert any("email_not_configured" in r.getMessage() for r in caplog.records)

    async def test_zonder_link_is_de_nieuwe_gebruiker_niet_in_te_loggen(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        installeer_smtp_dubbel(monkeypatch)
        kop, _tenant = await _beheerder(client)
        medewerker = unieke_email("nieuw")
        await client.post(self.URL, json={"email": medewerker, "role": "user"}, headers=kop)

        for poging in (WACHTWOORD, "", "password", "Welkom01"):
            ingelogd = await client.post(
                "/api/v1/auth/login", data={"username": medewerker, "password": poging}
            )
            assert ingelogd.status_code in (400, 401, 422), (poging, ingelogd.text)


# ---------------------------------------------------------------------------
# Wachtwoord vergeten: een dienst die zelf NIETS logt, mag het mislukken niet verbergen
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestHerstelmailTaakMeldtMislukken:
    """De route antwoordt altijd neutraal en verstuurt op de achtergrond. Een taak waarvan het resultaat
    wordt weggegooid liet een mislukking voor niemand zichtbaar (gemeten 2026-10-15); de taak logt nu zelf,
    ook als de dienst dat niet doet."""

    async def _vraag_herstel_aan(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch, dienst: Any
    ) -> list[str]:
        """Vraagt herstel aan en geeft de ERROR-regels van de loguru-logger van de route terug.

        `router_password` logt met loguru, dat niet naar `caplog` gaat: een tijdelijke sink vangt het op.
        """
        import asyncio

        from loguru import logger as loguru_logger

        from src.core.services import email as email_module

        email = unieke_email("vergeten")
        assert (await registreer(client, email)).status_code in (200, 201)
        monkeypatch.setattr(email_module, "get_email_service", lambda: dienst)

        regels: list[str] = []
        sink = loguru_logger.add(lambda bericht: regels.append(str(bericht)), level="ERROR")
        try:
            antwoord = await client.post("/api/v1/auth/forgot-password", json={"email": email})
            await asyncio.sleep(0.5)
        finally:
            loguru_logger.remove(sink)

        assert antwoord.status_code == 200
        return regels

    async def test_een_dienst_die_false_geeft_zonder_te_loggen_wordt_toch_gelogd(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _StilleDienst(EmailServiceInterface):
            async def send(self, message: EmailMessage) -> bool:
                return False

            async def send_template(
                self, to: str | list[str], template_name: str, context: dict[str, object]
            ) -> bool:
                return False

        regels = await self._vraag_herstel_aan(client, monkeypatch, _StilleDienst())

        assert any("password_reset_email_not_sent" in r for r in regels), regels

    async def test_een_dienst_die_een_uitzondering_werpt_wordt_gelogd(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _KapotteDienst(EmailServiceInterface):
            async def send(self, message: EmailMessage) -> bool:
                raise RuntimeError("mailserver onbereikbaar")

            async def send_template(
                self, to: str | list[str], template_name: str, context: dict[str, object]
            ) -> bool:
                raise RuntimeError("mailserver onbereikbaar")

        regels = await self._vraag_herstel_aan(client, monkeypatch, _KapotteDienst())

        assert any(
            "password_reset_email_failed: RuntimeError: mailserver onbereikbaar" in r for r in regels
        ), regels


# ---------------------------------------------------------------------------
# Gate 2 (security-review): een actief token per gebruiker, geen adres in het log, geen link naar localhost
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestEenActiefTokenPerGebruiker:
    """Met 48 uur voor een uitnodiging is een oud token dat blijft werken een lang open venster (een
    doorgestuurde of gedeelde mail). Een nieuwe uitgifte maakt het vorige token daarom ongeldig."""

    async def _uitgenodigd(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str, SmtpDubbel]:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        kop, _tenant = await _beheerder(client)
        medewerker = unieke_email("nieuw")
        await client.post(
            "/api/v1/admin/create_user", json={"email": medewerker, "role": "user"}, headers=kop
        )
        return medewerker, _link_uit(dubbel).split("token=")[1], dubbel

    async def test_een_nieuw_herstelverzoek_maakt_het_token_van_de_uitnodiging_ongeldig(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import asyncio

        medewerker, eerste, dubbel = await self._uitgenodigd(client, monkeypatch)

        await client.post("/api/v1/auth/forgot-password", json={"email": medewerker})
        await asyncio.sleep(0.5)
        tweede = re.search(r"reset-password\?token=([\w\-]+)", dubbel.ontvangen[-1].alle_delen)
        assert tweede and tweede.group(1) != eerste

        oud = await client.post(
            "/api/v1/auth/reset-password", json={"token": eerste, "new_password": NIEUW_WACHTWOORD}
        )
        nieuw = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": tweede.group(1), "new_password": NIEUW_WACHTWOORD},
        )

        assert oud.status_code == 400, oud.text
        assert nieuw.status_code == 200, nieuw.text

    async def test_na_het_kiezen_van_een_wachtwoord_is_er_geen_token_van_deze_gebruiker_meer(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.database.redis import get_redis_client

        medewerker, token, _dubbel = await self._uitgenodigd(client, monkeypatch)
        gekozen = await client.post(
            "/api/v1/auth/reset-password", json={"token": token, "new_password": NIEUW_WACHTWOORD}
        )
        assert gekozen.status_code == 200, gekozen.text

        redis_client = await get_redis_client()
        sleutels = await redis_client.keys("password_reset_user:*")
        waarden = [await redis_client.get(k) for k in sleutels]
        gedecodeerd = [w.decode() if isinstance(w, bytes) else w for w in waarden]

        assert await redis_client.get(f"password_reset:{token}") is None
        assert token not in gedecodeerd


@pytest.mark.integration
class TestUitnodigingLektNiets:
    async def test_een_adres_in_de_foutmelding_van_de_mailserver_komt_niet_in_het_log(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from src.core.api.auth import uitnodiging

        class _Weigerende(EmailServiceInterface):
            async def send(self, message: EmailMessage) -> bool:
                raise RuntimeError("Recipient refused: lek@klant.example")

            async def send_template(
                self, to: str | list[str], template_name: str, context: dict[str, object]
            ) -> bool:
                raise RuntimeError("Recipient refused: lek@klant.example")

        monkeypatch.setattr(uitnodiging, "get_email_service", lambda: _Weigerende())

        with caplog.at_level(logging.ERROR):
            gelukt = await uitnodiging.stuur_uitnodiging("lek@klant.example", 999_001)

        assert gelukt is False
        tekst = " ".join(r.getMessage() + str(r.exc_info) for r in caplog.records)
        assert "lek@klant.example" not in tekst
        assert any("invitation_email_failed" in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize("omgeving", ["production", "staging"])
    async def test_zonder_frontend_url_wordt_er_in_productie_geen_link_naar_localhost_gemaild(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        omgeving: str,
    ) -> None:
        from src.core.api.auth import uitnodiging

        monkeypatch.setenv("ENVIRONMENT", omgeving)
        monkeypatch.delenv("FRONTEND_URL", raising=False)
        verstuurd: list[EmailMessage] = []

        class _Opname(EmailServiceInterface):
            async def send(self, message: EmailMessage) -> bool:
                verstuurd.append(message)
                return True

            async def send_template(
                self, to: str | list[str], template_name: str, context: dict[str, object]
            ) -> bool:
                return True

        monkeypatch.setattr(uitnodiging, "get_email_service", lambda: _Opname())

        with caplog.at_level(logging.ERROR):
            gelukt = await uitnodiging.stuur_uitnodiging("nieuw@klant.example", 999_002)

        assert gelukt is False
        assert verstuurd == []
        assert any("invitation_frontend_url_missing" in r.getMessage() for r in caplog.records)
