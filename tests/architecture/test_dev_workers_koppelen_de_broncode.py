"""In de dev-stack draaien alle services die `src` laden de ACTUELE code, niet die van een oud image.

Gemeten 2026-10-10 (sessie 53): de mail ging weg maar de factuur bleef `open`, omdat de
workflow-worker een image van 7 oktober draaide dat `_markeer_herinnerd` nog niet had. Alleen
`backend` en `learning-worker` koppelden `./src`; `workflow-worker` en `scheduler` niet.

Bewaakte verzameling (benoemd, niet afgeleid): backend, workflow-worker, scheduler, learning-worker.
De test leest de YAML en kijkt naar de volumeregels per service, niet naar tekst in het bestand --
`./src` in een commentaar of onder een andere service telt dus niet.

Grens: alleen `docker-compose.dev.yml`. De basis-compose (productie) koppelt nooit `./src`; ook dat
wordt hier bewaakt, zodat een koppeling niet per ongeluk naar productie lekt.

Mutatiebewijs: zie de uitslag in de commit-boodschap en het verslag (een regel per element van de
verzameling, elk in het echte bestand, daarna teruggezet via een kopie).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DEV_COMPOSE = REPO / "docker-compose.dev.yml"
BASE_COMPOSE = REPO / "docker-compose.yml"

BRONKOPPELING = "./src:/app/src"
DEV_SERVICES_MET_BRON = ("backend", "workflow-worker", "scheduler", "learning-worker")


def _services(pad: Path) -> dict[str, Any]:
    inhoud = yaml.safe_load(pad.read_text(encoding="utf-8"))
    return inhoud.get("services", {})


def _volumes(service: dict[str, Any]) -> list[str]:
    return [str(v) for v in service.get("volumes", []) if isinstance(v, str)]


@pytest.mark.parametrize("naam", DEV_SERVICES_MET_BRON)
def test_dev_service_koppelt_de_broncode(naam: str) -> None:
    service = _services(DEV_COMPOSE).get(naam, {})

    assert BRONKOPPELING in _volumes(service), (
        f"docker-compose.dev.yml: service `{naam}` koppelt `{BRONKOPPELING}` niet. Zonder die "
        "koppeling draait de service code uit een oud image (gemeten 2026-10-10: de factuur bleef "
        "`open` na een verstuurde herinnering)."
    )


def test_de_bewaakte_dev_services_bestaan() -> None:
    aanwezig = _services(DEV_COMPOSE)

    ontbrekend = [n for n in DEV_SERVICES_MET_BRON if n not in aanwezig]
    assert not ontbrekend, (
        f"Service(s) {ontbrekend} staan niet meer in docker-compose.dev.yml; haal ze uit "
        "DEV_SERVICES_MET_BRON (anders bewaakt deze test niets)."
    )


@pytest.mark.parametrize("naam", DEV_SERVICES_MET_BRON)
def test_de_basis_compose_koppelt_nooit_de_broncode(naam: str) -> None:
    service = _services(BASE_COMPOSE).get(naam, {})

    assert BRONKOPPELING not in _volumes(service), (
        f"docker-compose.yml: service `{naam}` koppelt `{BRONKOPPELING}`. Dat hoort alleen in "
        "docker-compose.dev.yml; productie draait de code uit het image."
    )
