"""De productie-compose geeft de API een FRONTEND_URL, en weigert te starten zonder (workflowscherm nazorg, punt 3).

De API weigert sinds deze wijziging te starten zonder `FRONTEND_URL` buiten een zachte omgeving (`src/core/config/frontend_url.py`):
een uitnodiging of wachtwoordherstel zou anders een link naar localhost bevatten. `docker-compose.prod.yml` zette de variabele
niet; een uitrol daarmee zou dan stoppen bij het opstarten (Gate 2 code-review). De compose volgt hier zijn eigen conventie
voor verplichte waarden: `${NAAM:?uitleg}`, zodat `docker compose` het ontbreken al bij het uitrollen meldt.

Mutatiebewijs (2026-10-26): zie de eindmelding van de sessie.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

COMPOSE = Path("docker-compose.prod.yml")


def _api_omgeving() -> dict[str, str]:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    omgeving: dict[str, str] = {}
    for dienst in compose["services"].values():
        if dienst.get("build", {}).get("target") != "production-api":
            continue
        for regel in dienst.get("environment", []):
            if isinstance(regel, str) and "=" in regel:
                sleutel, waarde = regel.split("=", 1)
                omgeving[sleutel] = waarde
    return omgeving


@pytest.mark.unit
def test_de_api_dienst_zet_frontend_url() -> None:
    assert "FRONTEND_URL" in _api_omgeving()


@pytest.mark.unit
def test_frontend_url_is_verplicht_en_geen_stille_standaard() -> None:
    waarde = _api_omgeving().get("FRONTEND_URL", "")

    assert waarde.startswith("${FRONTEND_URL:?"), f"verplicht via `:?`, kreeg: {waarde}"


@pytest.mark.unit
def test_de_melding_bij_een_ontbrekende_frontend_url_is_nederlands_en_noemt_de_vorm() -> None:
    waarde = _api_omgeving().get("FRONTEND_URL", "")

    assert "verplicht" in waarde and "https" in waarde


@pytest.mark.unit
def test_frontend_url_is_niet_hardgecodeerd() -> None:
    waarde = _api_omgeving().get("FRONTEND_URL", "")

    assert "localhost" not in waarde and "127.0.0.1" not in waarde


def _omgeving_van(bestand: str, dienst: str) -> dict[str, str]:
    compose = yaml.safe_load(Path(bestand).read_text(encoding="utf-8"))
    omgeving: dict[str, str] = {}
    for regel in compose["services"][dienst].get("environment", []):
        if isinstance(regel, str) and "=" in regel:
            sleutel, waarde = regel.split("=", 1)
            omgeving[sleutel] = waarde
    return omgeving


@pytest.mark.unit
def test_het_basisbestand_geeft_frontend_url_door_aan_de_api() -> None:
    """`docker-compose.yml` alleen: zonder ENVIRONMENT valt de API terug op production en eist FRONTEND_URL; met deze regel
    kan een operator hem zetten (Gate 2 code-review, ronde 2)."""
    assert "FRONTEND_URL" in _omgeving_van("docker-compose.yml", "backend")


@pytest.mark.unit
def test_make_up_zet_de_api_in_development_zodat_localhost_de_terugval_blijft() -> None:
    """`make up` = docker-compose.yml + docker-compose.dev.yml; de overlay maakt de API zacht (localhost-terugval)."""
    assert _omgeving_van("docker-compose.dev.yml", "backend").get("ENVIRONMENT") == "development"


@pytest.mark.unit
def test_er_is_precies_een_api_dienst_in_de_compose() -> None:
    """Zonder deze toets zou een hernoemd `target` de andere toetsen stil leeg laten slagen."""
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    api_diensten = [
        naam
        for naam, d in compose["services"].items()
        if d.get("build", {}).get("target") == "production-api"
    ]

    assert len(api_diensten) == 1
