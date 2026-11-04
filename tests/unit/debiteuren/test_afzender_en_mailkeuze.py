"""Afzender en keuze van de mailservice -- Keten B dag 2 (besluit 2 en 3).

Wat dit toetst, per vraag:

1. `SMTPEmailService` zet `EMAIL_FROM` als `From` en niet de inlognaam (`email.py:157`).
   De inlognaam blijft wel de INLOG bij de server. Zonder `EMAIL_FROM` blijft de inlognaam de
   terugval (gedrag van vandaag).
2. `get_email_service()` kiest SMTP zodra `SMTP_HOST` expliciet gezet is, ook buiten
   production/staging; zonder `SMTP_HOST` blijft het de console buiten die twee omgevingen.
   Beslistabel: ENVIRONMENT x SMTP_HOST (gezet / leeg / afwezig).
3. Regressie: wachtwoordherstel verstuurt nog steeds.

Systeemgrens: alleen `aiosmtplib.send` is vervangen (zie `_smtp_dubbel.py`).

**Wat de opstelling uitzet, nagelopen.** Autouse in `tests/conftest.py`: `enforce_testing_env`
(TESTING=1), `_reset_global_state` (tenantfilter), `ensure_main_thread_event_loop`,
`_seed_module_snapshot`. Geen daarvan raakt mail, `ENVIRONMENT` of `SMTP_*`. De module zet
`ENVIRONMENT` zelf per test; bij het importeren van conftest staat die op "test".
"""

from __future__ import annotations

import pytest

from src.core.services.email import (
    ConsoleEmailService,
    EmailMessage,
    SMTPEmailService,
    get_email_service,
    send_password_reset_email,
)
from tests.unit.debiteuren._smtp_dubbel import installeer_smtp_dubbel, zet_testmailbox

RESET_URL = "https://app.example/reset?t=abc"


def _brief() -> EmailMessage:
    return EmailMessage(to="debiteur@klant.example", subject="Onderwerp", body="Tekst")


@pytest.mark.unit
@pytest.mark.asyncio
class TestAfzender:
    async def test_from_is_email_from_en_niet_de_inlognaam(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch, wachtwoord="geheim-ww-1")
        dubbel = installeer_smtp_dubbel(monkeypatch)

        await SMTPEmailService().send(_brief())

        assert [b.afzender for b in dubbel.ontvangen] == ["noreply@sanskritisetu.org"]

    async def test_de_inlognaam_blijft_de_inlog_bij_de_server(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Andere kant op: de afzender wijzigen mag de inlog niet meenemen."""
        zet_testmailbox(monkeypatch, wachtwoord="geheim-ww-1")
        dubbel = installeer_smtp_dubbel(monkeypatch)

        await SMTPEmailService().send(_brief())

        assert dubbel.ontvangen[0].opties.get("username") == "inlog@smtp.example"

    async def test_zonder_email_from_is_de_inlognaam_de_terugval(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Andere kant op: de huidige terugval blijft; `EMAIL_FROM` is geen verplichting."""
        zet_testmailbox(monkeypatch, wachtwoord="geheim-ww-1")
        monkeypatch.delenv("EMAIL_FROM")
        dubbel = installeer_smtp_dubbel(monkeypatch)

        await SMTPEmailService().send(_brief())

        assert dubbel.ontvangen[0].afzender == "inlog@smtp.example"

    async def test_zonder_inlog_komt_de_afzender_toch_uit_email_from(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mailpit heeft geen inlog: `From` mag dan niet leeg zijn (nu: `self.username or ''`)."""
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)

        await SMTPEmailService().send(_brief())

        assert dubbel.ontvangen[0].afzender == "noreply@sanskritisetu.org"

    async def test_ontvanger_onderwerp_en_tekst_blijven_zoals_opgegeven(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)

        await SMTPEmailService().send(_brief())

        brief = dubbel.ontvangen[0]
        assert (brief.ontvanger, brief.onderwerp, brief.tekst) == (
            "debiteur@klant.example",
            "Onderwerp",
            "Tekst",
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestWachtwoordherstelBlijftVerzenden:
    async def test_wachtwoordherstel_verstuurt_een_brief_aan_de_gebruiker(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch, wachtwoord="geheim-ww-1")
        monkeypatch.setenv("ENVIRONMENT", "production")
        dubbel = installeer_smtp_dubbel(monkeypatch)

        await send_password_reset_email("gebruiker@klant.example", RESET_URL)

        assert [b.ontvanger for b in dubbel.ontvangen] == ["gebruiker@klant.example"]

    async def test_wachtwoordherstel_komt_van_het_noreply_adres(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zet_testmailbox(monkeypatch, wachtwoord="geheim-ww-1")
        monkeypatch.setenv("ENVIRONMENT", "production")
        dubbel = installeer_smtp_dubbel(monkeypatch)

        await send_password_reset_email("gebruiker@klant.example", RESET_URL)

        assert [b.afzender for b in dubbel.ontvangen] == ["noreply@sanskritisetu.org"]

    async def test_de_resetlink_staat_in_de_brief(self, monkeypatch: pytest.MonkeyPatch) -> None:
        zet_testmailbox(monkeypatch, wachtwoord="geheim-ww-1")
        monkeypatch.setenv("ENVIRONMENT", "production")
        dubbel = installeer_smtp_dubbel(monkeypatch)

        await send_password_reset_email("gebruiker@klant.example", RESET_URL)

        assert RESET_URL in dubbel.ontvangen[0].alle_delen


@pytest.mark.unit
class TestKeuzeVanDeMailservice:
    """Beslistabel ENVIRONMENT x SMTP_HOST."""

    @pytest.mark.parametrize("omgeving", ["development", "test"])
    def test_buiten_production_met_smtp_host_is_het_smtp(
        self, monkeypatch: pytest.MonkeyPatch, omgeving: str
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", omgeving)
        monkeypatch.setenv("SMTP_HOST", "mailpit")

        assert isinstance(get_email_service(), SMTPEmailService)

    @pytest.mark.parametrize("omgeving", ["development", "test"])
    def test_buiten_production_zonder_smtp_host_is_het_de_console(
        self, monkeypatch: pytest.MonkeyPatch, omgeving: str
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", omgeving)
        monkeypatch.delenv("SMTP_HOST", raising=False)

        assert isinstance(get_email_service(), ConsoleEmailService)

    def test_een_lege_smtp_host_telt_niet_als_expliciet_gezet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Compose zet `SMTP_HOST=` leeg als de variabele niet gevuld is: dat is "niet gezet"."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("SMTP_HOST", "")

        assert isinstance(get_email_service(), ConsoleEmailService)

    @pytest.mark.parametrize("omgeving", ["production", "staging"])
    def test_production_en_staging_blijven_smtp_zonder_smtp_host(
        self, monkeypatch: pytest.MonkeyPatch, omgeving: str
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", omgeving)
        monkeypatch.delenv("SMTP_HOST", raising=False)

        assert isinstance(get_email_service(), SMTPEmailService)

    @pytest.mark.parametrize("omgeving", ["production", "staging"])
    def test_production_en_staging_met_smtp_host_zijn_smtp(
        self, monkeypatch: pytest.MonkeyPatch, omgeving: str
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", omgeving)
        monkeypatch.setenv("SMTP_HOST", "smtp.echt.example")

        assert isinstance(get_email_service(), SMTPEmailService)

    def test_de_gekozen_service_gebruikt_de_gezette_smtp_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("SMTP_HOST", "mailpit")
        monkeypatch.setenv("SMTP_PORT", "1025")

        dienst = get_email_service()

        assert isinstance(dienst, SMTPEmailService) and (dienst.host, dienst.port) == (
            "mailpit",
            1025,
        )
