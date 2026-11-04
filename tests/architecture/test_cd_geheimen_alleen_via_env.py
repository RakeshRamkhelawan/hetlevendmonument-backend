"""In de CD-workflows staat geen `${{ secrets.X }}` rechtstreeks in een `run:`-blok (brief 2026-10-24).

GitHub vervangt `${{ secrets.X }}` TEKSTUEEL voordat de shell het script ziet. Staat de expressie in het
`run:`-blok, dan staat de waarde in het tijdelijke scriptbestand op de runner en breekt een waarde met een
aanhalingsteken, `$` of backtick de shelltekst (injectie). Via `env:` komt de waarde als omgevingsvariabele
binnen en leest de shell hem als gegevens. De bestaande commentaren in `cd-production.yml` (OP-94/OP-98,
MEDIUM-6) zeggen dit al; het was alleen niet bewaakt. Gemeten 2026-10-24 op 98e5047b: 41 regels in
cd-production.yml en 82 in cd-staging.yml.

**Uitgebreid in uitrol-nazorg-3 (2026-10-24):** `rollback.yml` valt nu onder dezelfde guard (3 stappen, 9 regels naar
`env:`), en niet alleen `secrets.X` telt maar elke `${{ ... }}`-expressie die `secrets` noemt (`secrets['X']`,
`secrets["X"]`, `toJSON(secrets)`, `format(.., secrets.X)`). Ook het `script:` van een github-script-actie is
uitvoerbare tekst; de andere `with:`-waarden (zoals `token:`) en `env:` niet. `#` en `//` zijn commentaar.

**Benoemde verzameling (een mutatie per element):** `WORKFLOWS` -- `cd-production.yml`, `cd-staging.yml` en
`rollback.yml`.
De test loopt per job en per stap over de YAML-structuur en kijkt ALLEEN in `run:` (niet in `env:`, `with:`,
`if:` of commentaar). Een `#`-regel telt niet mee, zodat de naam in een toelichting de test niet rood maakt.

MUTATIEBEWIJS (2026-10-24, op een kopie van elke workflow):
    een `${{ secrets.X }}` terug in een `run:`-blok van cd-production.yml  -> ROOD
    idem in cd-staging.yml                                                  -> ROOD
    dezelfde expressie in `env:` of `with:`                                 -> GROEN
    dezelfde expressie in een `#`-commentaarregel van het `run:`-blok       -> GROEN
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ".github/workflows/cd-production.yml",
    ".github/workflows/cd-staging.yml",
    ".github/workflows/rollback.yml",
)
#: DOTALL: een expressie mag over meerdere regels lopen (`${{` op de ene regel, `secrets.X }}` op de volgende).
_EXPRESSIE = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
#: IGNORECASE: GitHub leest contextnamen hoofdletterongevoelig (niet door mij gemeten; voor de zekerheid gedekt).
_SECRETS = re.compile(r"\bsecrets\b", re.IGNORECASE)


def _geheimen_in(blok: str) -> list[str]:
    """Elke `${{ ... }}`-expressie die `secrets` noemt: `secrets.X`, `secrets['X']`, `toJSON(secrets)`, ...

    Zoekt over het hele blok (zonder de commentaarregels), niet per regel.
    """
    zonder_commentaar = "\n".join(r for r in blok.splitlines() if not _is_commentaar(r))
    return [
        " ".join(m.group(0).split())[:90]
        for m in _EXPRESSIE.finditer(zonder_commentaar)
        if _SECRETS.search(m.group(1))
    ]


def _is_commentaar(regel: str) -> bool:
    """`#` voor een shell-`run:`, `//` voor het JavaScript in een `with: script:` (github-script)."""
    kaal = regel.strip()
    return kaal.startswith("#") or kaal.startswith("//")


def directe_geheimen(tekst: str) -> list[str]:
    """`job / stap: regel` voor elke niet-commentaarregel in een `run:` of `with: script:` met een geheim.

    Uitvoerbare tekst is `run:` EN het `script:` van een github-script-actie. De overige `with:`-waarden
    (zoals `token:`) en `env:` zijn juist de bedoelde plek en tellen niet.
    """
    workflow: dict[str, Any] = yaml.safe_load(tekst)
    gevonden: list[str] = []
    for job, inhoud in workflow["jobs"].items():
        for nummer, stap in enumerate(inhoud.get("steps", [])):
            uitvoerbaar = [str(stap.get("run", ""))]
            met = stap.get("with")
            if isinstance(met, dict) and "script" in met:
                uitvoerbaar.append(str(met["script"]))
            for blok in uitvoerbaar:
                for expressie in _geheimen_in(blok):
                    naam = stap.get("name", f"stap {nummer}")
                    gevonden.append(f"{job} / {naam}: {expressie}")
    return gevonden


@pytest.mark.parametrize("pad", WORKFLOWS)
def test_geen_geheim_rechtstreeks_in_een_run_blok(pad: str) -> None:
    tekst = (REPO_ROOT / pad).read_text(encoding="utf-8")

    assert directe_geheimen(tekst) == []


def test_een_geheim_in_een_run_blok_wordt_gevonden() -> None:
    tekst = (
        "jobs:\n  a:\n    steps:\n      - name: x\n        run: |\n"
        "          echo ${{ secrets.X }}\n"
    )

    assert len(directe_geheimen(tekst)) == 1


def test_een_geheim_in_env_of_with_is_goed() -> None:
    tekst = (
        "jobs:\n  a:\n    steps:\n"
        "      - name: x\n        env:\n          V: ${{ secrets.X }}\n        run: echo $V\n"
        "      - uses: foo/bar@v1\n        with:\n          token: ${{ secrets.Y }}\n"
    )

    assert directe_geheimen(tekst) == []


def test_een_geheim_in_een_commentaarregel_telt_niet() -> None:
    tekst = (
        "jobs:\n  a:\n    steps:\n      - run: |\n"
        "          # zie ${{ secrets.X }}\n          echo hoi\n"
    )

    assert directe_geheimen(tekst) == []


@pytest.mark.parametrize(
    "regel",
    [
        "echo ${{ secrets['X'] }}",
        'echo ${{ secrets["X"] }}',
        "echo ${{ toJSON(secrets) }}",
        "echo ${{ format('{0}', secrets.X) }}",
    ],
    ids=["enkele-haken", "dubbele-haken", "tojson", "in-een-functie"],
)
def test_ook_andere_vormen_van_een_geheim_in_een_run_blok_worden_gevonden(regel: str) -> None:
    tekst = f"jobs:\n  a:\n    steps:\n      - name: x\n        run: |\n          {regel}\n"

    assert len(directe_geheimen(tekst)) == 1


@pytest.mark.parametrize(
    "blok",
    [
        "echo ${{\n          secrets.X }}",
        "echo ${{ secrets.X\n          }}",
        "echo ${{ Secrets.X }}",
        "echo ${{ SECRETS['X'] }}",
    ],
    ids=[
        "expressie-over-twee-regels",
        "sluiting-op-volgende-regel",
        "hoofdletter",
        "hoofdletters-haken",
    ],
)
def test_een_expressie_over_meerdere_regels_of_met_hoofdletters_wordt_gevonden(blok: str) -> None:
    tekst = f"jobs:\n  a:\n    steps:\n      - name: x\n        run: |\n          {blok}\n"

    assert len(directe_geheimen(tekst)) == 1


def test_een_geheim_in_een_with_script_wordt_gevonden() -> None:
    tekst = (
        "jobs:\n  a:\n    steps:\n      - uses: actions/github-script@v7\n        with:\n"
        "          script: |\n            const s = '${{ secrets.X }}';\n"
    )

    assert len(directe_geheimen(tekst)) == 1


def test_een_geheim_in_een_andere_with_waarde_is_goed() -> None:
    tekst = (
        "jobs:\n  a:\n    steps:\n      - uses: foo/bar@v1\n        with:\n"
        "          token: ${{ secrets.X }}\n          script: console.log('hoi')\n"
    )

    assert directe_geheimen(tekst) == []


def test_een_geheim_in_een_commentaarregel_van_een_with_script_telt_niet() -> None:
    tekst = (
        "jobs:\n  a:\n    steps:\n      - uses: actions/github-script@v7\n        with:\n"
        "          script: |\n            // zie ${{ secrets.X }}\n            core.info('hoi');\n"
    )

    assert directe_geheimen(tekst) == []


def test_de_verzameling_workflows_bestaat_nog() -> None:
    """Een hernoemde workflow zou de test stil leeg laten draaien."""
    assert all((REPO_ROOT / pad).is_file() for pad in WORKFLOWS)
