"""De omgeving wint van elk bestand, en het spoor noemt WELK bestand (ADR-036 OP-243).

Twee restpunten van OP-243, hier afgerond.

**A. `.env.local` overstemde een geexporteerde variabele.** `src/core/env_loader.py` laadde
dat bestand met `override=True`. python-dotenv maakt daarbij geen onderscheid tussen "al
gezet door een eerder dotenv-bestand" en "door de operator geexporteerd" -- het overschrijft
allebei. De bedoeling (een lokaal bestand wint van de andere BESTANDEN) stond al in de
docstring; de uitvoering haalde ook de echte omgeving onderuit. `.env.local` is gitignored,
dus dat was een onzichtbaar bestand dat een expliciete keuze overstemde.

Daarbovenop sloeg een guard de HELE loader over zodra `DATABASE_URL` gezet was -- ook voor
sleutels die wel uit een bestand hadden moeten komen. Die guard is vervallen omdat het
onderliggende probleem nu voor ALLE sleutels is opgelost.

**B. Het spoor onderscheidde `.env` niet van `.env.local`.** `SecretSource.DOTENV_FILE` zegt
"uit een dotenv-bestand" maar niet welk. Juist dat onderscheid deed ertoe: `.env` is
getrackt en gedeeld, `.env.local` bestaat alleen op die ene machine.

**Beide richtingen, met opzet.** Zonder de tegentest zou "laad helemaal niets" punt A halen
en "schrijf altijd .env.local" punt B -- en dan is het resultaat nog steeds fout.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from src.core.config.secret_provider import SecretProvider, SecretSource
from src.core.env_loader import setup_environment


def test_een_geexporteerde_variabele_overleeft_env_local(tmp_path: Path) -> None:
    """De reparatie: wat de operator zet, wint van elk bestand."""
    (tmp_path / ".env").write_text("OP243_A=uit-env\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("OP243_A=uit-env-local\n", encoding="utf-8")

    with patch.dict(os.environ, {"OP243_A": "uit-de-omgeving"}):
        setup_environment(root=tmp_path)

        assert os.environ["OP243_A"] == "uit-de-omgeving", (
            "Een gitignored .env.local overschreef een geexporteerde variabele. Dat is "
            "precies het onzichtbare-bestand-probleem van ADR-036 OP-243."
        )


def test_env_local_wint_nog_steeds_van_env(tmp_path: Path) -> None:
    """De andere richting -- zonder deze zou 'laad niets' een geldige oplossing zijn."""
    (tmp_path / ".env").write_text("OP243_B=uit-env\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("OP243_B=uit-env-local\n", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OP243_B", None)
        setup_environment(root=tmp_path)

        assert os.environ["OP243_B"] == "uit-env-local", (
            "Voor een sleutel die NIET geexporteerd is hoort .env.local van .env te winnen; "
            "dat is de bedoelde werking en die mag de reparatie niet slopen."
        )


def test_bestanden_worden_geladen_ook_als_database_url_al_gezet_is(tmp_path: Path) -> None:
    """De vervallen guard: een sleutel mocht de hele loader niet uitzetten."""
    (tmp_path / ".env").write_text("OP243_C=uit-env\n", encoding="utf-8")

    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://x:x@localhost:1/x"}):
        os.environ.pop("OP243_C", None)
        setup_environment(root=tmp_path)

        assert os.environ.get("OP243_C") == "uit-env", (
            "Met DATABASE_URL gezet werd de HELE loader overgeslagen, dus ook sleutels die "
            "niets met de database te maken hebben."
        )
        assert os.environ["DATABASE_URL"] == "postgresql://x:x@localhost:1/x", (
            "En de geexporteerde DATABASE_URL moet onaangeroerd blijven."
        )


def _laatste_regel(provider: SecretProvider, sleutel: str):
    regels = [e for e in provider.audit_log if e.secret_key == sleutel]
    assert regels, f"Geen auditregel voor {sleutel!r}."
    return regels[-1]


def test_het_spoor_noemt_env_local_als_de_waarde_daaruit_komt(tmp_path, monkeypatch) -> None:
    """Punt B: welk BESTAND leverde de waarde."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OP243_D=uit-env\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("OP243_D=uit-env-local\n", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OP243_D", None)
        provider = SecretProvider(environment="development")
        assert provider.get_secret("OP243_D") == "uit-env-local"

        regel = _laatste_regel(provider, "OP243_D")
        assert regel.source == SecretSource.DOTENV_FILE
        assert regel.source_detail == ".env.local", (
            f"Het spoor noemt {regel.source_detail!r}. `.env` is getrackt en gedeeld, "
            "`.env.local` bestaat alleen op deze machine -- dat verschil hoort zichtbaar "
            "te zijn voor wie de auditketen leest."
        )


def test_het_spoor_noemt_env_als_de_waarde_daaruit_komt(tmp_path, monkeypatch) -> None:
    """De andere richting -- anders zou 'schrijf altijd .env.local' halen."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OP243_E=uit-env\n", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OP243_E", None)
        provider = SecretProvider(environment="development")
        assert provider.get_secret("OP243_E") == "uit-env"

        regel = _laatste_regel(provider, "OP243_E")
        assert regel.source_detail == ".env", (
            f"Het spoor noemt {regel.source_detail!r} in plaats van '.env'."
        )
