"""De mail bij "Wachtwoord vergeten" is een echte mail en geen dump (2026-10-15).

Gemeten bij het onderzoek van de lege mailbox: `send_password_reset_email` vroeg `password_reset.html`
aan de sjabloonengine, die zoekt in `src/core/templates/email/`. De sjablonen stonden in
`templates/email/` in de repo-root (en de Dockerfile kopieert alleen `src/`, `config/` en `scripts/`),
dus de engine viel terug op "Template: password_reset.html / Context: {...}" en de platte tekst
had geen link. Zelfs als het sjabloon gevonden werd, verwachtte het `reset_link` en `name` terwijl
de code `reset_url` en `user_name` meegeeft: dan stond er geen link in. Het sjabloon was Engels en
noemde 24 uur terwijl de link een uur werkt.

Wat gemeten wordt, over de ECHTE sjabloonengine en `SMTPEmailService` (alleen `aiosmtplib.send`, de
laatste functie voor het netwerk, is vervangen):

(a) de link staat in de platte tekst en als knop in de html;
(b) er staat geen "Template:"- of "Context:"-dump in;
(c) onderwerp en tekst zijn Nederlands en noemen de echte geldigheid (een uur);
(d) alle zes de sjablonen worden door de engine GEVONDEN, en de sjablonen staan op EEN plek: de map
    die de engine gebruikt is ook de map van `email.TEMPLATE_DIR`, en `templates/email/` in de root is
    leeg in git.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.core.services import email as email_module
from src.core.services.email import send_password_reset_email
from src.core.services.email_templates import EmailTemplateEngine
from tests.unit.debiteuren._smtp_dubbel import installeer_smtp_dubbel, zet_testmailbox

REPO = Path(__file__).resolve().parents[2]
LINK = "https://app.example/reset-password?token=abc123-_XYZ"
ZES_SJABLONEN = (
    "account_deleted_confirmation.html",
    "dsar_export_ready.html",
    "pack_deactivated.html",
    "pack_deactivation_warning.html",
    "password_reset.html",
    "welcome.html",
)


@pytest.mark.unit
class TestDeHerstelmail:
    @pytest.fixture
    async def brief(self, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
        zet_testmailbox(monkeypatch)
        dubbel = installeer_smtp_dubbel(monkeypatch)
        gelukt = await send_password_reset_email("medewerker@klant.example", LINK)
        assert gelukt is True
        return dubbel.ontvangen[0]

    async def test_de_link_staat_in_de_platte_tekst(self, brief) -> None:  # type: ignore[no-untyped-def]
        assert LINK in brief.tekst

    async def test_de_link_staat_als_knop_in_de_html(self, brief) -> None:  # type: ignore[no-untyped-def]
        assert f'href="{LINK}"' in brief.alle_delen

    async def test_er_staat_geen_sjabloondump_in(self, brief) -> None:  # type: ignore[no-untyped-def]
        assert "Template:" not in brief.alle_delen
        assert "Context:" not in brief.alle_delen

    async def test_het_onderwerp_is_nederlands(self, brief) -> None:  # type: ignore[no-untyped-def]
        assert "wachtwoord" in brief.onderwerp.lower()
        assert "Password" not in brief.onderwerp

    async def test_de_tekst_is_nederlands_en_noemt_de_echte_geldigheid(self, brief) -> None:  # type: ignore[no-untyped-def]
        assert "wachtwoord" in brief.tekst.lower()
        assert "1 uur" in brief.tekst
        assert "Click" not in brief.alle_delen and "Dear" not in brief.alle_delen
        assert "24 hours" not in brief.alle_delen

    async def test_de_html_noemt_de_echte_geldigheid_ook(self, brief) -> None:  # type: ignore[no-untyped-def]
        assert "1 uur" in brief.alle_delen


@pytest.mark.unit
class TestDeSjablonenStaanOpEenPlek:
    @pytest.mark.parametrize("naam", ZES_SJABLONEN)
    def test_de_engine_vindt_het_sjabloon(self, naam: str) -> None:
        engine = EmailTemplateEngine()
        assert engine.env is not None

        engine.env.get_template(naam)  # TemplateNotFound als hij op de verkeerde plek zoekt

    def test_de_map_van_de_engine_is_ook_de_map_van_email_template_dir(self) -> None:
        engine = EmailTemplateEngine()
        assert engine.env is not None
        zoekmap = Path(str(engine.env.loader.searchpath[0])).resolve()  # type: ignore[union-attr]

        assert Path(email_module.TEMPLATE_DIR).resolve() == zoekmap

    def test_de_sjablonen_staan_niet_ook_in_de_root(self) -> None:
        """Op twee plekken is hetzelfde probleem terug: een kopie wordt bijgewerkt en de andere niet."""
        gevolgd = subprocess.run(
            ["git", "ls-files", "templates/email"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()

        assert gevolgd == []
