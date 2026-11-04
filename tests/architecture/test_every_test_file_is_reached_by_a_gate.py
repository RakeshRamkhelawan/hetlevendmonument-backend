"""Een testbestand dat door geen enkele CI-stap wordt gedraaid, bewaakt niets (ADR-036 OP-54).

**Hoe dit gevonden is.** Bij het draaien van gerichte tests voor OP-53 viel
`tests/test_app_fixture_debug.py` om met `ImportError: cannot import name
'_register_admin_management'`. Dat symbool bestaat sinds de ADR-033-routerherstructurering niet
meer; `router_registry.py` is voor het laatst gewijzigd op 2026-06-05. Dat bestand kon dus twee
maanden lang niet laden zonder dat iemand het merkte -- het lag in `tests/` maar buiten
`tests/unit`, `tests/architecture` en `tests/core`, en dat zijn de enige mappen die de blokkerende
CI-stap draait.

Dezelfde klasse als OP-11, waar het alleen draaien van `tests/unit/` 22 failures onopgemerkt liet.
Daar ging het om UITVOERING, hier om COLLECTIE: een bestand dat niet eens laadt, meldt niets.

**Wat er daarna gemeten is, en dat is groter dan de bevinding.** Er stonden 20 testbestanden in de
WORTEL van `tests/`. Alle 20 laadden succesvol -- samen 82 tests, gemeten 2026-08-05 met
`--collect-only`. Het waren dus geen dode bestanden maar WERKENDE tests die geen enkele CI-stap
draaide.

**De open helft is op 2026-08-11 gesloten.** Toen pas is gemeten of ze ook SLAGEN, en dat scheidde
ze scherp in drie stapels:

- **57 tests in zes bestanden slaagden** en zijn naar `tests/unit/` verplaatst, waar de poort ze
  wel draait: `test_orchestrator.py` (16), `test_p404_shared_fixtures_library.py` (16),
  `test_ai_features.py` (12), `test_workflow_engine.py` (9), `test_phase1_bus.py` (2),
  `test_phase2_sop.py` (2).
- **Twaalf bestanden waren weggeschreven debugwerk** en zijn verwijderd, samen met zeven
  `verify_*`/`manual_*`-scripts die pytest niet eens verzamelt. Hun eigen docstrings zeiden het al:
  "Minimal test without conftest.py", "Simple test to debug goal router", "Test the original
  command that was hanging". Gemeten voor het verwijderen: 4 rood, 1 error, 7 groen -- er ging geen
  werkende dekking verloren.
- **`test_seed_phase3.py` (11 tests) is verwijderd**, niet verplaatst. De fixture `test_db` bestaat
  al lang niet meer; omzetten naar `db_session` bracht de echte reden boven water:
  `sqlite3.ProgrammingError: Error binding parameter 2: type 'UUID' is not supported`. Het
  seed-script werkt met UUID-tenants en heeft PostgreSQL nodig, dus dit is een integratietest die
  in de wortel van `tests/` was blijven liggen. Herbouwen is een eigen keuze en staat als zodanig
  in OP-54.

**Wat deze guard daarom wel en niet doet.** Hij blokkeert NIEUWE testbestanden in de wortel van
`tests/`, en houdt wat er over is in een gedateerde uitzonderingslijst. Hij doet met opzet GEEN
uitspraak over de mappen buiten de poorten (`tests/e2e`, `tests/chaos`, `tests/compliance`,
`tests/enterprise`, ...): die vallen daar mogelijk met goede reden buiten -- Playwright, handmatige
chaosproeven -- en een uitzonderingslijst met verzonnen redenen is erger dan geen lijst. Dat blijft
in OP-54 staan als het bredere vraagstuk.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: De mappen die de blokkerende CI-stap draait, GELEZEN uit de workflow in plaats van hier
#: overgetypt. Een tweede kopie van deze lijst zou stil uit elkaar lopen met de echte poort, en
#: dan bewaakt deze guard iets anders dan wat er gebeurt.
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci-feature.yml"

#: De 20 testbestanden in de wortel van `tests/`, gemeten 2026-08-05.
#:
#: Reden is voor alle 20 dezelfde en daarom hier een keer opgeschreven in plaats van 20 keer:
#: historisch daar neergezet, nooit in een poort opgenomen, en samen leveren ze 82 tests op die
#: succesvol laden maar door geen enkele CI-stap gedraaid worden. Of ze SLAGEN is niet gemeten.
#:
#: Dit is bewust GEEN vrijbrief: `test_no_new_root_level_test_files` blokkeert een 21e, en
#: `test_the_exception_list_is_not_stale` dwingt dat een bestand dat verdwijnt of verhuist ook uit
#: deze lijst gaat. De 20 opruimen (verplaatsen naar `tests/unit`, of verwijderen als ze elders
#: gedekt zijn) is de open helft van OP-54 en vraagt een eigen dag met Rakesh' besluit.
KNOWN_UNREACHED_ROOT_TESTS: frozenset[str] = frozenset(
    {
        # Enige overgebleven uitzondering, opgeruimd 2026-08-11. De twee tests hier falen omdat
        # GEEN ENKELE `local__`-tool in een permissieprofiel staat, dus de broker weigert ze voor
        # de registry uberhaupt in beeld komt ("Agent 'None' is not authorized"). Of die registry
        # aan hoort te staan is een vraag voor Rakesh, geen kwestie die deze opruiming moet
        # beslissen. Hem in een poort hangen zou de suite rood maken voor een bevinding die
        # elders geregistreerd staat.
        #
        # CORRECTIE 2026-09-07: deze reden verwees naar ADR-036 OP-127. Dat was een
        # misattributie en die stond hier een maand -- OP-127 gaat over
        # `shell_orchestrator.py`, een andere module, en is op 2026-09-07 gesloten door die
        # module te verwijderen. Een uitzonderingslijst met een reden per regel is niet beter
        # dan zijn redenen, en een verwijzing naar een GESLOTEN rij is precies de rot die dit
        # patroon hoort te voorkomen. De echte open vraag (staat de LocalToolRegistry aan, en
        # zo ja welk profiel krijgt hij) is nu ADR-036 OP-208. Gemeten op 2026-09-07: de enige
        # treffer op `local__` in `config/tool_permissions.yml` staat in een comment, dus geen
        # enkel profiel geeft een `local__*`-tool.
        "tests/test_tool_broker_local.py",
    }
)


def _gate_directories() -> set[str]:
    """De `tests/...`-paden die in de CI-workflow worden aangeroepen, uit de bron.

    **Commentaar wordt eerst gestript (2026-09-07).** De vorige versie regexte de VOLLEDIGE
    tekst van de workflow, dus een mapnaam in een `#`-regel gold als "bereikt door een poort".
    De poortstap heeft drie `# SKIP:`-commentaarregels direct boven het pytest-commando, en de
    blinde Gate 2-review wees erop dat je een map van de commandoregel kon halen terwijl haar
    naam in een comment bleef staan -- dan zag deze guard nog steeds een poort. Dat is
    woordelijk de val die `quality-gates.md` twee keer optekent: "de naam in een `#`-comment
    laten staan hield de guard groen".

    De strip is fail-CLOSED: knipt hij per ongeluk een `#` binnen een string af, dan wordt de
    verzameling KLEINER en is deze guard strenger over losse testbestanden, niet ruimer.
    """
    return _gate_directories_from_text(WORKFLOW.read_text(encoding="utf-8"))


def _gate_directories_from_text(text: str) -> set[str]:
    """De extractie, los van het bestand -- zodat hij op TEKST te toetsen is.

    Deze splitsing bestaat omdat het bewijs voor de comment-strip anders alleen proza in een
    docstring zou zijn, en `valkuilen/SKILL.md` legt vast dat mutatiebewijs UITVOERBAAR hoort
    te zijn (`test_the_extraction_ignores_directories_that_only_appear_in_a_comment`).
    """
    zonder_commentaar = "\n".join(regel.partition("#")[0] for regel in text.splitlines())
    found = set(re.findall(r"tests/[a-zA-Z0-9_/]+", zonder_commentaar))
    # `--ignore=`-paden en losse bestandsverwijzingen zijn geen gedraaide MAPPEN.
    return {path for path in found if not path.endswith(".py")}


def _root_level_test_files() -> set[str]:
    """Getrackte testbestanden direct onder `tests/`, uit git.

    `git ls-files` en niet `Path.glob`: `.gitignore` en `.git/info/exclude` hebben in dit project
    eerder 1816 getrackte bestanden onzichtbaar gemaakt voor zoekacties (OP-17), en een scan die
    bestanden mist meldt niets en lijkt daarmee groen.
    """
    completed = subprocess.run(
        ["git", "ls-files", "tests/test_*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line for line in completed.stdout.splitlines() if line}


#: Twee tekstgevallen die de extractie moet onderscheiden. Het tweede is de vorm die de
#: guard tot 2026-09-07 groen hield: de mapnaam alleen in een `#`-regel.
_EXTRACTIE_GEVALLEN = (
    (
        "de map staat op de commandoregel",
        "        run: |\n          pytest tests/unit tests/safety -n 2 -q\n",
        True,
    ),
    (
        "de map staat ALLEEN in een comment",
        "        # SKIP: tests/safety draait hier niet mee\n"
        "        run: |\n          pytest tests/unit -n 2 -q\n",
        False,
    ),
    (
        "een comment ACHTER de commandoregel telt de map wel",
        "        run: |\n          pytest tests/unit tests/safety -n 2  # met opzet\n",
        True,
    ),
)


@pytest.mark.parametrize("naam, tekst, verwacht", _EXTRACTIE_GEVALLEN, ids=[g[0] for g in _EXTRACTIE_GEVALLEN])
def test_the_extraction_ignores_directories_that_only_appear_in_a_comment(
    naam: str, tekst: str, verwacht: bool
) -> None:
    """`tests/safety` in een comment is geen poort die die map draait.

    Gemeten 2026-09-07 door een blinde Gate 2-review: de extractie regexte de VOLLEDIGE
    workflowtekst, en de poortstap heeft drie `# SKIP:`-commentaarregels direct boven het
    pytest-commando. Je kon dus een map van de commandoregel halen terwijl haar naam in een
    comment bleef staan, en deze guard zag nog steeds een poort. Dat is woordelijk de val die
    `quality-gates.md` twee keer optekent.

    Deze rijen zijn het mutatiebewijs zelf: ze draaien bij elke run, dus ze kunnen niet
    verouderen zoals een opgeschreven bewijs dat wel doet. Rood te maken door de
    `partition("#")` uit `_gate_directories_from_text` te halen -- dan slaat rij 2 om.
    """
    assert ("tests/safety" in _gate_directories_from_text(tekst)) is verwacht, (
        "geval %r: verwacht %s, extractie gaf %s"
        % (naam, verwacht, sorted(_gate_directories_from_text(tekst)))
    )


def test_the_gate_directories_are_readable_from_the_workflow() -> None:
    """Vangnet: als het lezen van de workflow stilvalt, zeggen de tests hieronder niets."""
    gates = _gate_directories()

    assert {"tests/unit", "tests/architecture", "tests/core"} <= gates, (
        f"De drie blokkerende poortmappen staan niet in {sorted(gates)}. Is de workflow "
        "hernoemd of de teststap herschreven? Zolang dit leeg terugkomt, bewaakt deze guard niets."
    )


def test_the_scan_finds_the_root_level_files() -> None:
    """Vangnet in de andere richting: vindt de scan uberhaupt bestanden?"""
    found = _root_level_test_files()

    assert found, (
        "Geen testbestanden gevonden in de wortel van `tests/`. Dat zou goed nieuws zijn, maar het "
        "is waarschijnlijker dat het git-patroon niet meer klopt -- en dan is deze guard vacuum."
    )


def test_no_new_root_level_test_files() -> None:
    """Een nieuw testbestand in de wortel van `tests/` wordt door geen poort gedraaid."""
    unexpected = sorted(_root_level_test_files() - KNOWN_UNREACHED_ROOT_TESTS)

    assert not unexpected, (
        f"Deze testbestanden staan in de wortel van `tests/`: {unexpected}. Geen enkele CI-stap "
        "draait die map, dus ze bewaken niets -- en als ze niet meer laden, meldt niets dat ook. "
        "Zet het bestand in `tests/unit`, `tests/architecture` of `tests/core`, of voeg het met "
        "een reden toe aan KNOWN_UNREACHED_ROOT_TESTS als het bewust buiten de poort valt."
    )


def test_the_exception_list_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst, anders rot hij dicht."""
    resolved = sorted(KNOWN_UNREACHED_ROOT_TESTS - _root_level_test_files())

    assert not resolved, (
        f"Deze bestanden staan nog in KNOWN_UNREACHED_ROOT_TESTS maar bestaan daar niet meer: "
        f"{resolved}. Verplaatst of verwijderd? Haal ze uit de lijst, anders suggereert die lijst "
        "een probleem dat er niet meer is en verliest hij zijn waarde als werklijst."
    )
