"""Stap 1b van `scripts/pre-deploy-check.sh` valideert de compose-STRUCTUUR, niet de omgeving (OP-261).

Gemeten 2026-09-18 en opnieuw 2026-10-24: `docker compose -f docker-compose.yml -f
docker-compose.prod.yml config --quiet` interpoleert, en de prod-overlay eist met opzet variabelen
(`${X:?...}`). Op een machine zonder die variabelen faalt de stap dus per definitie (exit 1); een
gate die nooit groen KAN worden, leert zijn gebruiker dat rood normaal is.

`config --no-interpolate --quiet` (zoals CLAUDE.md voorschrijft) laat de variabelen ongemoeid en
valideert alleen de structuur, en zet geen waarden uit `.env` in de uitvoer.

**Wat deze test doet:** haalt het commando UIT het script (de `if docker compose ...; then`-regel van
stap 1b), draait het in een omgeving zonder een van de productievariabelen, en eist exit 0; draait
het daarna met een prod-overlay waarin de YAML-syntaxis kapot is en eist exit != 0. Zonder de tweede
helft is "altijd groen" een geldige oplossing.

MUTATIEBEWIJS (2026-10-24):
    `--no-interpolate` uit het script halen                 -> `..._groen_zonder_de_productievariabelen` ROOD
    de stap weghalen, commando niet meer vindbaar           -> `..._staat_in_het_script` ROOD
    het commando altijd laten slagen (`true`)               -> `..._kapotte_compose_is_rood` ROOD
    legitiem: een ontbrekende variabele in de omgeving      -> GROEN (dat is de hele bedoeling)
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/pre-deploy-check.sh"

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker ontbreekt")


def _stap_1b_commando() -> list[str] | None:
    tekst = SCRIPT.read_text(encoding="utf-8")
    blok = re.search(r"# 1b\..*?echo \"2\.", tekst, flags=re.S)
    if blok is None:
        return None
    for regel in blok.group(0).splitlines():
        regel = regel.strip()
        if regel.startswith("if docker compose") and regel.endswith("then"):
            commando = re.sub(r"\s*>\s*/dev/null.*$", "", regel[len("if ") : -len("; then")])
            return shlex.split(commando)
    return None


def _verplichte_variabelen() -> set[str]:
    """Elke `${NAAM:?...}` in de compose-bestanden: de variabelen die de prod-overlay eist."""
    tekst = (REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    tekst += (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    return set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*):\?", tekst))


def _schone_omgeving() -> dict[str, str]:
    """De eigen omgeving ZONDER een van de variabelen die de prod-overlay eist."""
    eisen = _verplichte_variabelen()
    return {k: v for k, v in os.environ.items() if k not in eisen}


def _draai(commando: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        commando,
        cwd=REPO_ROOT,
        env=_schone_omgeving(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_de_prod_overlay_eist_variabelen_zodat_de_meting_iets_betekent() -> None:
    """Eist de overlay niets meer, dan bewijst `..._groen_zonder_de_productievariabelen` niets."""
    assert len(_verplichte_variabelen()) >= 1


def test_het_compose_commando_staat_in_het_script() -> None:
    commando = _stap_1b_commando()

    assert commando is not None and commando[:3] == ["docker", "compose", "-f"]


def test_stap_1b_is_groen_zonder_de_productievariabelen() -> None:
    commando = _stap_1b_commando()
    assert commando is not None

    uitslag = _draai(commando)

    assert uitslag.returncode == 0, uitslag.stderr[-400:]


def test_een_kapotte_compose_is_rood(tmp_path: Path) -> None:
    commando = _stap_1b_commando()
    assert commando is not None
    kapot = tmp_path / "docker-compose.prod.yml"
    kapot.write_text("services:\n  backend:\n    environment: [oops\n", encoding="utf-8")
    kapot_commando = [str(kapot) if a == "docker-compose.prod.yml" else a for a in commando]

    uitslag = _draai(kapot_commando)

    assert uitslag.returncode != 0
