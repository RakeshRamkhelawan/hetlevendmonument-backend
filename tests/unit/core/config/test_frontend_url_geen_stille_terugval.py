"""Een mail met een link naar localhost is voor een medewerker waardeloos (workflowscherm nazorg, punt 3).

De acceptant (agentstap dag 2) kreeg een uitnodiging en een wachtwoordherstel met een link naar `http://localhost:3000`. Het
wachtwoordherstel viel daar zonder melding op terug als `FRONTEND_URL` ontbrak. Nu geldt: BUITEN een zachte omgeving
(`ZACHTE_OMGEVINGEN`: development, dev, local, test, testing) is een ontbrekende of onbruikbare `FRONTEND_URL` een fout bij het
opstarten; in een zachte omgeving blijft `http://localhost:3000` de bedoelde terugval.

Mutatiebewijs (2026-10-26): zie de eindmelding van de sessie.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config.frontend_url import FrontendUrlOntbreekt, frontend_url

ZACHT = ["development", "dev", "local", "test", "testing", "DEVELOPMENT"]
STRENG = ["production", "staging", "prod", "live", "acceptatie", "onbekend"]


@pytest.fixture(autouse=True)
def _schone_omgeving(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)


class TestInEenZachteOmgeving:
    @pytest.mark.parametrize("omgeving", ZACHT)
    def test_zonder_frontend_url_blijft_localhost_de_terugval(self, omgeving: str) -> None:
        assert frontend_url(omgeving) == "http://localhost:3000"

    @pytest.mark.parametrize("omgeving", ZACHT)
    def test_een_ingestelde_url_gaat_voor_de_terugval(
        self, omgeving: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FRONTEND_URL", "http://localhost:5174")

        assert frontend_url(omgeving) == "http://localhost:5174"


class TestBuitenEenZachteOmgeving:
    @pytest.mark.parametrize("omgeving", STRENG)
    def test_zonder_frontend_url_weigert_de_app(self, omgeving: str) -> None:
        with pytest.raises(FrontendUrlOntbreekt):
            frontend_url(omgeving)

    @pytest.mark.parametrize("omgeving", STRENG)
    def test_een_lege_frontend_url_telt_als_ontbrekend(
        self, omgeving: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FRONTEND_URL", "   ")

        with pytest.raises(FrontendUrlOntbreekt):
            frontend_url(omgeving)

    @pytest.mark.parametrize("omgeving", STRENG)
    def test_een_ingestelde_url_wordt_gebruikt(
        self, omgeving: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FRONTEND_URL", "https://app.sanskritisetu.org")

        assert frontend_url(omgeving) == "https://app.sanskritisetu.org"

    def test_een_ontbrekende_omgeving_is_productie_en_dus_streng(self) -> None:
        with pytest.raises(FrontendUrlOntbreekt):
            frontend_url()

    def test_de_omgeving_komt_uit_de_omgevingsvariabele_als_ze_niet_is_meegegeven(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "development")

        assert frontend_url() == "http://localhost:3000"

    def test_de_melding_zegt_wat_er_mis_is_en_wat_te_doen_staat(self) -> None:
        with pytest.raises(FrontendUrlOntbreekt) as fout:
            frontend_url("production")

        assert "FRONTEND_URL" in str(fout.value) and "production" in str(fout.value)


class TestEenOnbruikbareUrl:
    @pytest.mark.parametrize(
        "waarde", ["app.sanskritisetu.org", "localhost:3000", "ftp://x.example", "//x.example"]
    )
    def test_een_url_zonder_http_of_https_weigert(
        self, waarde: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FRONTEND_URL", waarde)

        with pytest.raises(FrontendUrlOntbreekt):
            frontend_url("production")

    def test_een_slash_aan_het_eind_wordt_weggehaald_zodat_de_link_geen_dubbele_slash_krijgt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FRONTEND_URL", "https://app.sanskritisetu.org///")

        assert frontend_url("production") == "https://app.sanskritisetu.org"


class TestStrengeToetsBuitenEenZachteOmgeving:
    @pytest.mark.parametrize(
        "waarde",
        [
            "http://app.sanskritisetu.org",  # tokenlink in leesbare tekst
            "https://localhost:3000",
            "https://127.0.0.1",
            "https://gebruiker@app.sanskritisetu.org",  # userinfo-vorm: de echte host is wat na de @ staat
            "https://app.sanskritisetu.org?x=1",
            "https://app.sanskritisetu.org#top",
            "https://",
        ],
    )
    def test_een_onbruikbare_url_weigert(self, waarde: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FRONTEND_URL", waarde)

        with pytest.raises(FrontendUrlOntbreekt):
            frontend_url("production")

    def test_een_pad_blijft_toegestaan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FRONTEND_URL", "https://sanskritisetu.org/app")

        assert frontend_url("production") == "https://sanskritisetu.org/app"

    @pytest.mark.parametrize("waarde", ["http://localhost:5174", "http://127.0.0.1:5174"])
    def test_in_een_zachte_omgeving_blijft_lokaal_http_toegestaan(
        self, waarde: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FRONTEND_URL", waarde)

        assert frontend_url("development") == waarde


class TestSpatiesRondDeUrl:
    def test_spaties_rond_een_geldige_url_worden_weggehaald(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FRONTEND_URL", "  https://app.sanskritisetu.org/  ")

        assert frontend_url("production") == "https://app.sanskritisetu.org"


class TestHetOpstartenEistDeUrl:
    def test_de_lifespan_roept_de_controle_aan(self) -> None:
        """Structuur, geen tekst: een aanroep in de code, niet een naam in een commentaar of docstring."""
        bron = Path("src/core/app_lifespan.py").read_text(encoding="utf-8")
        aanroepen = {
            knoop.func.id
            for knoop in ast.walk(ast.parse(bron))
            if isinstance(knoop, ast.Call) and isinstance(knoop.func, ast.Name)
        }

        assert "frontend_url" in aanroepen

    def test_de_controle_draait_niet_in_testmodus(self) -> None:
        """De app-tests starten de lifespan zonder FRONTEND_URL; de controle hoort er alleen buiten testmodus te draaien."""
        boom = ast.parse(Path("src/core/app_lifespan.py").read_text(encoding="utf-8"))
        ouders: dict[ast.AST, ast.AST] = {kind: ouder for ouder in ast.walk(boom) for kind in ast.iter_child_nodes(ouder)}
        aanroep = next(
            k
            for k in ast.walk(boom)
            if isinstance(k, ast.Call) and isinstance(k.func, ast.Name) and k.func.id == "frontend_url"
        )
        voorwaarden: list[str] = []
        huidig: ast.AST | None = aanroep
        while huidig is not None:
            if isinstance(huidig, ast.If):
                voorwaarden.append(ast.unparse(huidig.test))
            huidig = ouders.get(huidig)

        assert "not is_test_mode" in voorwaarden


class TestDeMailsGebruikenDeCentraleUrl:
    def test_de_herstelmail_zet_de_ingestelde_url_in_de_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.api.auth.router_password import _reset_url

        monkeypatch.setenv("FRONTEND_URL", "https://app.sanskritisetu.org")

        assert _reset_url("tok123") == "https://app.sanskritisetu.org/reset-password?token=tok123"

    def test_de_herstelmail_valt_buiten_een_zachte_omgeving_niet_stil_terug_op_localhost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.api.auth.router_password import _reset_url

        monkeypatch.setenv("ENVIRONMENT", "production")

        with pytest.raises(FrontendUrlOntbreekt):
            _reset_url("tok123")

    @pytest.mark.asyncio
    async def test_de_uitnodiging_zet_de_ingestelde_url_in_de_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.api.auth import uitnodiging

        monkeypatch.setenv("FRONTEND_URL", "https://app.sanskritisetu.org")
        mail = MagicMock()
        mail.send = AsyncMock(return_value=True)
        gebouwd: dict[str, str] = {}

        def bouw(email: str, link: str) -> str:
            gebouwd["link"] = link
            return "bericht"

        with (
            patch.object(uitnodiging, "get_redis_client", AsyncMock(return_value=MagicMock())),
            patch.object(uitnodiging, "geef_resettoken_uit", AsyncMock(return_value="tok123")),
            patch.object(uitnodiging, "get_email_service", return_value=mail),
            patch.object(uitnodiging, "bouw_uitnodiging", bouw),
        ):
            gelukt = await uitnodiging.stuur_uitnodiging("a@example.org", 7)

        assert (
            gelukt is True
            and gebouwd["link"] == "https://app.sanskritisetu.org/reset-password?token=tok123"
        )

    @pytest.mark.asyncio
    async def test_de_uitnodiging_stuurt_buiten_een_zachte_omgeving_geen_localhost_link(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.api.auth import uitnodiging

        monkeypatch.setenv("ENVIRONMENT", "staging")
        mail = MagicMock()
        mail.send = AsyncMock(return_value=True)

        with patch.object(uitnodiging, "get_email_service", return_value=mail):
            gelukt = await uitnodiging.stuur_uitnodiging("a@example.org", 7)

        assert gelukt is False and mail.send.await_count == 0
