"""Lege SMTP-inloggegevens zijn "niet ingesteld", nooit een lege tekst (2026-10-16).

Gemeten: `.env.development` en `.env.local` hebben `SMTP_USER=` en `SMTP_PASSWORD=` zonder waarde. Dat
komt als "" in `os.environ`. `SMTPEmailService` gaf die lege tekst door aan `aiosmtplib.send`, en
aiosmtplib logt in zodra de gebruikersnaam niet `None` is (`_maybe_login_on_connect`, aiosmtplib
5.1.2). Mailpit heeft geen authenticatie en verbrak de verbinding: "Wachtwoord vergeten" mislukte.

Wat gemeten wordt, over de echte `SMTPEmailService` met alleen `aiosmtplib.send` vervangen (de opties
die daar aankomen zijn wat de server te zien krijgt):

(a) leeg of alleen spaties voor gebruiker en wachtwoord -> `None`, dus geen LOGIN;
(b) een lege `SMTP_USERNAME` verbergt een gevulde `SMTP_USER` niet;
(c) gevulde waarden blijven gevuld, ook zonder omringende spaties;
(d) een wachtwoord zonder gebruiker wordt niet meegegeven.
"""

from __future__ import annotations

import pytest

from src.core.services.email import EmailMessage, SMTPEmailService
from tests.unit.debiteuren._smtp_dubbel import installeer_smtp_dubbel, zet_testmailbox


async def _opties_bij_verzenden(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    dubbel = installeer_smtp_dubbel(monkeypatch)
    gelukt = await SMTPEmailService().send(
        EmailMessage(to="medewerker@klant.example", subject="Onderwerp", body="Tekst")
    )
    assert gelukt is True
    return dubbel.ontvangen[0].opties


@pytest.mark.unit
class TestLegeInloggegevens:
    @pytest.fixture(autouse=True)
    def _mailbox(self, monkeypatch: pytest.MonkeyPatch) -> None:
        zet_testmailbox(monkeypatch)

    async def test_lege_variabelen_geven_geen_login(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SMTP_USER", "")
        monkeypatch.setenv("SMTP_PASSWORD", "")

        opties = await _opties_bij_verzenden(monkeypatch)

        assert opties["username"] is None
        assert opties["password"] is None

    async def test_alleen_spaties_geven_geen_login(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SMTP_USERNAME", "   ")
        monkeypatch.setenv("SMTP_PASSWORD", "  ")

        opties = await _opties_bij_verzenden(monkeypatch)

        assert opties["username"] is None
        assert opties["password"] is None

    async def test_een_lege_smtp_username_verbergt_smtp_user_niet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SMTP_USERNAME", "")
        monkeypatch.setenv("SMTP_USER", "inlog@smtp.example")
        monkeypatch.setenv("SMTP_PASSWORD", "geheim-wachtwoord")

        opties = await _opties_bij_verzenden(monkeypatch)

        assert opties["username"] == "inlog@smtp.example"

    async def test_gevulde_gegevens_blijven_gevuld(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SMTP_USERNAME", " inlog@smtp.example ")
        monkeypatch.setenv("SMTP_PASSWORD", "geheim-wachtwoord")

        opties = await _opties_bij_verzenden(monkeypatch)

        assert opties["username"] == "inlog@smtp.example"
        assert opties["password"] == "geheim-wachtwoord"

    async def test_een_wachtwoord_zonder_gebruiker_wordt_niet_meegegeven(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SMTP_USER", "")
        monkeypatch.setenv("SMTP_PASSWORD", "geheim-wachtwoord")

        opties = await _opties_bij_verzenden(monkeypatch)

        assert opties["password"] is None
