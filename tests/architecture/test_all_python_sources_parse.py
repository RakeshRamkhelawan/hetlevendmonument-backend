"""Elk getrackt Python-bronbestand moet parseerbaar zijn (ADR-036 OP-203).

**De bevinding.** `except SyntaxError` staat op 2026-09-04 op 45 plekken in
Python-bronbestanden (`grep -rn "except SyntaxError" --include="*.py" .`,
zelf geteld -- de OP-203-registerrij noemt 35, gemeten 2026-09-03; het
verschil komt van bestanden die de PR-#163-samenvoeging op develop erbij
bracht). De meerderheid daarvan slaat een onparseerbaar bestand stil over
(`return []`, `continue`, `pass`) in plaats van het te melden; een kleiner
deel faalt al luid (`pytest.fail`, `assert False`) of gebruikt de fout als
bedoelde diagnostische uitvoer (bijv. `src/core/sandbox/doctor_agent.py`,
dat een syntaxfout als resultaat van een code-controle hoort terug te geven).
Een BOM produceert precies zo'n `SyntaxError`
(`invalid non-printable character U+FEFF`) -- dat is hoe 17 bestanden drie
maanden onzichtbaar bleven voor dertig scanners tegelijk, inclusief de tenant-,
pseudonimiserings- en SQL-injectieguards (zie OP-203 in het register voor het
volledige mechanisme, en OP-204 voor de vijf DSM-plafondtests die daardoor
rood werden).

**Waarom een SUPERSET-guard en niet dertig aanpassingen.** Elke plek
individueel "hard laten falen op een onparseerbaar bestand" vereist een eigen
oordeel per scanner -- sommige lopen bewust over gegenereerde of legacy
bestanden. Deze guard maakt in plaats daarvan het ONDERLIGGENDE probleem
onbereikbaar: als geen enkel getrackt bestand (op de gedateerde
template-uitzonderingen na) ooit onparseerbaar kan zijn, kan geen van de
dertig downstream-scanners er ooit blind voor worden. Dat is precies de
tweede uitweg die de OP-203-registerrij zelf noemt.

**Waarom `git ls-files` en niet `Path.rglob`.** Zelfde reden als
`test_no_bom_in_python_sources.py`: `rglob` vanaf de repo-root loopt door
`.venv`, `node_modules` en `.git`. `git ls-files` geeft exact de getrackte
verzameling, en de returncode wordt gecontroleerd.

**Waarom zowel `SyntaxError` ALS `UnicodeDecodeError` gevangen worden.**
Alleen `SyntaxError` vangen zou deze guard zelf hetzelfde euvel geven als
OP-203 beschrijft: een bestand met echt ongeldige UTF-8-bytes zou de
`.decode()` laten CRASHEN voordat `ast.parse` uberhaupt draait, en de scan
zou stoppen in plaats van het als bevinding te melden.

**Zelf gemeten, niet aangenomen (2026-09-04).** `git ls-files -z -- *.py`
geeft 4773 bestanden. Van die 4773 falen er 8, allemaal templates onder
`.agents/skills/sanskritisetu-developer/assets/` met opzettelijke
`{{PLACEHOLDER}}`-syntax (bijv. `class {{AGENT_NAME}}(BaseAgent):` --
zelf gelezen, geen bug). Twee andere waren ECHTE, kapotte syntax en zijn
gerepareerd in dezelfde wijziging als deze guard, dus geen extra
uitzonderingen: `.agents/skills/sanskritisetu-developer/scripts/
generate_endpoint.py` (regel 584, een overtollige `'''` die niet bij een
string hoorde) en `tests/als/live_demo/als_llm_gemini_demo.py` (een
hardcoded pad met een enkele in plaats van dubbele backslash voor de letter
D -- onder pytest se `filterwarnings = ["error"]` werd de normaliter onschuldige
`SyntaxWarning` een harde `SyntaxError`; deze tweede is door deze guard
ZELF gevonden tijdens het bouwen ervan, niet vooraf bekend). `git ls-files`
kost 0,07s; lezen + decoderen + parsen van alle 4773 bestanden kost 6,78s --
ruim binnen de `--timeout=60` van de poort.

**Mutatiebewijs -- beide richtingen, uitgevoerd en gemeten 2026-09-04, met
`scripts/mutation_harness.py`.**

- een bestaand, parseerbaar bestand een echte syntaxfout geven: verwacht ROOD
  via `test_no_new_unparseable_python_sources`, gemeten ROOD; hersteld:
  verwacht GROEN, gemeten GROEN;
- een bestand dat WEL parseert opnemen in `KNOWN_UNPARSEABLE_FILES`: verwacht
  ROOD via `test_known_unparseable_files_are_not_stale`, gemeten ROOD;
- een niet-bestaand pad opnemen in `KNOWN_UNPARSEABLE_FILES`: verwacht ROOD
  via `test_known_unparseable_files_still_exist`, gemeten ROOD;
- ongemuteerd: alle vier tests GROEN.
"""

from __future__ import annotations

import ast
import functools
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: De enige map waar een uitzondering vandaan mag komen. Gate-2-bevinding
#: (2026-09-06, security-reviewer): zonder deze grens accepteert
#: KNOWN_UNPARSEABLE_FILES elk pad met elke reden -- aangetoond door een
#: bestand onder `src/core/als/` met een echte kapotte syntax toe te voegen
#: onder een verzonnen "template"-reden; alle vier tests bleven groen. De twee
#: tests hieronder (`..._are_scoped_to_the_template_directory` en
#: `..._still_look_like_templates`) dichten dat gat: een uitzondering buiten
#: deze map, of een bestand dat zijn `{{`-markering kwijt is, is nu zelf ROOD.
_TEMPLATE_PREFIX = ".agents/skills/sanskritisetu-developer/assets/"
_TEMPLATE_MARKER = "{{"

#: Gemeten 2026-09-04 (`git ls-files -z -- *.py` + `ast.parse` op elk resultaat).
#: Reden per regel -- allemaal opzettelijke `{{PLACEHOLDER}}`-scaffoldingtemplates,
#: nooit bedoeld als geldig Python, en buiten `src/`+`tests/` (dus onzichtbaar
#: voor elke scanner die daarbinnen blijft).
KNOWN_UNPARSEABLE_FILES: dict[str, str] = {
    ".agents/skills/sanskritisetu-developer/assets/agent-template/agent.py": (
        "scaffolding-template met {{AGENT_NAME}}/{{CAPABILITY}}-placeholders -- OP-203, Fase D"
    ),
    ".agents/skills/sanskritisetu-developer/assets/agent-template/capability.py": (
        "scaffolding-template met {{PLACEHOLDER}}-syntax -- OP-203, Fase D"
    ),
    ".agents/skills/sanskritisetu-developer/assets/agent-template/test_agent.py": (
        "scaffolding-template met {{PLACEHOLDER}}-syntax -- OP-203, Fase D"
    ),
    ".agents/skills/sanskritisetu-developer/assets/endpoint-template/router.py": (
        "scaffolding-template met {{PLACEHOLDER}}-syntax -- OP-203, Fase D"
    ),
    ".agents/skills/sanskritisetu-developer/assets/endpoint-template/schemas.py": (
        "scaffolding-template met {{PLACEHOLDER}}-syntax -- OP-203, Fase D"
    ),
    ".agents/skills/sanskritisetu-developer/assets/endpoint-template/service.py": (
        "scaffolding-template met {{PLACEHOLDER}}-syntax -- OP-203, Fase D"
    ),
    ".agents/skills/sanskritisetu-developer/assets/endpoint-template/test_endpoint.py": (
        "scaffolding-template met {{PLACEHOLDER}}-syntax -- OP-203, Fase D"
    ),
    ".agents/skills/sanskritisetu-developer/assets/model-template/model.py": (
        "scaffolding-template met {{PLACEHOLDER}}-syntax -- OP-203, Fase D"
    ),
}


def _tracked_python_files() -> list[str]:
    """Elk getrackt `.py`-bestand, als repo-relatief pad. Faalt LUID zonder git."""
    resultaat = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if resultaat.returncode != 0:
        raise AssertionError(
            "git ls-files gaf returncode %s -- zonder git meet deze guard nul bestanden en zou "
            "hij stilletjes groen melden: %s"
            % (resultaat.returncode, resultaat.stderr.decode("utf-8", "replace").strip())
        )
    return [n for n in resultaat.stdout.decode("utf-8").split("\0") if n]


@functools.lru_cache(maxsize=1)
def _unparseable_files() -> dict[str, str]:
    """Elk getrackt bestand dat niet parseert, met de foutmelding.

    `lru_cache`: twee tests in dit bestand roepen dit aan (`test_no_new_unparseable_
    python_sources` en `test_known_unparseable_files_are_not_stale`), en zonder cache
    draait de volledige 4773-bestanden-scan tot twee keer PER WORKER. Gemeten onder de echte
    poortconfiguratie (`-n 4 --timeout=60`, 2026-09-06): zonder cache duurde de
    duurste test 50,11s -- gevaarlijk dicht bij de 60s-grens zodra xdist twee van
    deze tests op dezelfde worker plant. Met cache draait de scan hooguit een keer
    per workerproces. Onschadelijk voor het mutatiebewijs: elke mutatieproef start
    een VERSE `python -m pytest`-subprocess, dus nooit een verouderde cache.
    """
    gevonden: dict[str, str] = {}
    for naam in _tracked_python_files():
        pad = REPO_ROOT / naam
        if not pad.exists():
            continue
        try:
            ast.parse(pad.read_bytes().decode("utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            gevonden[naam] = str(exc)
    return gevonden


@pytest.mark.architecture
def test_the_scan_finds_python_files_at_all() -> None:
    """Vangnet: zonder bestanden bewaakt deze guard niets.

    Rood te maken door `git ls-files` een patroon te geven dat niets matcht.
    """
    aantal = len(_tracked_python_files())
    assert aantal > 1000, (
        f"Slechts {aantal} getrackte .py-bestanden gevonden; op 2026-09-04 waren het er 4773. "
        "Is de scan stukgelopen, dan meldt deze guard nooit meer iets."
    )


@pytest.mark.architecture
def test_no_new_unparseable_python_sources() -> None:
    """Geen NIEUW onparseerbaar bestand buiten de gedateerde uitzonderingslijst.

    Rood te maken door een bestaand bestand een echte syntaxfout te geven, of
    een BOM (die geeft `SyntaxError: invalid non-printable character U+FEFF`,
    exact het mechanisme van OP-203).
    """
    gevonden = _unparseable_files()
    nieuw = {naam: fout for naam, fout in gevonden.items() if naam not in KNOWN_UNPARSEABLE_FILES}
    assert not nieuw, (
        "Deze getrackte Python-bestanden parsen niet en staan niet op de gedateerde "
        "uitzonderingslijst:\n"
        + "\n".join(f"  {naam}: {fout}" for naam, fout in sorted(nieuw.items()))
        + "\n\nEen onparseerbaar bestand is onzichtbaar voor elke scanner die `except "
        "SyntaxError` gebruikt (tenant-, pseudonimiserings- en SQL-injectieguards inbegrepen "
        "-- zie ADR-036 OP-203). Meestal is de oorzaak een BOM (drie bytes EF BB BF voor het "
        "eerste teken) of een editor die het bestand met de verkeerde encoding opsloeg. Is de "
        "syntax opzettelijk ongeldig (een template), voeg het pad dan toe aan "
        "KNOWN_UNPARSEABLE_FILES met een reden."
    )


@pytest.mark.architecture
def test_known_unparseable_files_are_not_stale() -> None:
    """Wie een uitzondering repareert, MOET de regel uit de lijst halen.

    Rood te maken door een bestand in KNOWN_UNPARSEABLE_FILES te zetten dat WEL parseert.
    """
    gevonden = _unparseable_files()
    opgelost = [naam for naam in KNOWN_UNPARSEABLE_FILES if naam not in gevonden]
    assert not opgelost, (
        "Mooi werk -- deze bestanden parsen nu wel. Haal ze uit KNOWN_UNPARSEABLE_FILES in "
        f"DEZELFDE commit: {sorted(opgelost)}"
    )


@pytest.mark.architecture
def test_known_unparseable_files_still_exist() -> None:
    """Een uitzondering die naar een verdwenen bestand wijst, is niet meer na te meten.

    Rood te maken door een pad in KNOWN_UNPARSEABLE_FILES te zetten dat niet bestaat.
    """
    ontbrekend = [naam for naam in KNOWN_UNPARSEABLE_FILES if not (REPO_ROOT / naam).exists()]
    assert not ontbrekend, (
        "Deze paden in KNOWN_UNPARSEABLE_FILES bestaan niet (meer) -- verwijderd, hernoemd, of "
        f"een typfout: {sorted(ontbrekend)}"
    )


@pytest.mark.architecture
def test_known_unparseable_files_are_scoped_to_the_template_directory() -> None:
    """Een uitzondering mag alleen uit de scaffolding-templatemap komen.

    Gate-2-bevinding (2026-09-06, security-reviewer): zonder deze grens accepteert
    KNOWN_UNPARSEABLE_FILES een pad ONDER `src/` of `tests/` met een verzonnen
    "template"-reden, en dat bestand wordt dan alsnog onzichtbaar voor de dertig
    downstream-scanners die deze guard juist moet backstoppen -- precies het risico
    dat OP-203 beschrijft, nu via de uitzonderingslijst zelf binnengesmokkeld.

    Rood te maken door een pad buiten `_TEMPLATE_PREFIX` aan KNOWN_UNPARSEABLE_FILES
    toe te voegen.
    """
    buiten_scope = [
        naam for naam in KNOWN_UNPARSEABLE_FILES if not naam.startswith(_TEMPLATE_PREFIX)
    ]
    assert not buiten_scope, (
        f"Deze uitzonderingen liggen buiten '{_TEMPLATE_PREFIX}' en zijn dus geen "
        f"scaffolding-template: {sorted(buiten_scope)}. Een onparseerbaar bestand ELDERS "
        "hoort een echte fix te krijgen, geen uitzondering."
    )


@pytest.mark.architecture
def test_known_unparseable_files_still_look_like_templates() -> None:
    """Een uitzondering blijft alleen geldig zolang het bestand nog een `{{`-marker draagt.

    Zonder deze toets kan een template stilletjes vervangen worden door een ANDER,
    echt kapot bestand met dezelfde bestandsnaam en een gekopieerde reden -- de
    naam-en-parseert-niet-toets uit `test_no_new_unparseable_python_sources` merkt
    dat niet, want beide zijn "onparseerbaar".

    Rood te maken door de `{{`-markering uit een van de acht templates te verwijderen
    (of een uitzondering toe te voegen voor een bestand zonder die markering).
    """
    zonder_marker = [
        naam
        for naam in KNOWN_UNPARSEABLE_FILES
        if (REPO_ROOT / naam).exists()
        and _TEMPLATE_MARKER not in (REPO_ROOT / naam).read_bytes().decode("utf-8", "replace")
    ]
    assert not zonder_marker, (
        f"Deze uitzonderingen bevatten geen '{_TEMPLATE_MARKER}' meer -- ze zien er niet "
        f"meer uit als een scaffolding-template: {sorted(zonder_marker)}. Is het bestand "
        "echt stuk (geen template meer), haal het dan uit KNOWN_UNPARSEABLE_FILES en fix "
        "de syntax."
    )
