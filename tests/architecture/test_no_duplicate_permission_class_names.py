"""Architecture test: geen twee verschillende klassen met dezelfde permissie-naam.

Achtergrond (ADR-036 D5, OP-15 -- opgelost 2026-08-01):
D5 vroeg om verwijdering van `ToolPermissionManager` in
`src/core/agents/tool_permissions.py`: "een tweede klasse met dezelfde naam is exact het
soort verwarring dat bij de drie ChiefOrchestrator-klassen al tot fouten leidde".

Bij de eerste verificatie leek de ADR-premisse niet te kloppen -- het was geen duplicaat
maar een ander ontwerp met dezelfde naam, en er hing een testsuite aan. Die conclusie was
gebaseerd op het TELLEN van verwijzingen, niet op het lezen ervan, en op zoekacties met een
blinde vlek (zie onderaan). Bij hercontrole:

- `tests/integration/test_budget_tool_permissions.py` bevatte 8 tests die niets toetsten:
  `assert True`, de lengte van een zojuist aangemaakte literal, en enum-waarden. Geen
  enkele riep een permissiefunctie aan.
- `tests/unit/test_tool_permissions.py` (20 echte gedragstests) was in de eerste ronde
  onzichtbaar, en `tests/integration/test_milestone2_resilience_security.py` ook.
- Productie-importeurs: nul, sinds het bestand in april 2026 via een bulk-restore van 972
  bestanden binnenkwam en nooit is aangesloten.

Conclusie: de ADR had gelijk. Twintig tests voor een model met nul aanroepers is geen
dekking maar onderhoud van een museumstuk; het enige effect op het draaiende systeem was
naamverwarring in de laag waar dat het gevaarlijkst is. Module en beide gewijde
testbestanden zijn verwijderd; de defaults-test in `test_milestone2_resilience_security.py`
is omgehangen naar de levende manager.

Daarmee zijn ALLE vier de botsingen weg -- ook `ToolCategory` (die ook in
`tool_broker/schemas.py` staat) en `PermissionDeniedError` (ook in
`src/core/exceptions/exceptions.py`). KNOWN_COLLISIONS is daarom leeg: deze guard bewaakt
nu puur dat er geen nieuwe bijkomen.

Waarschuwing voor wie deze guard later uitbreidt: de eerste analyse miste twee van de drie
testbestanden doordat `.git/info/exclude` 1816 tracked bestanden verborg voor ripgrep (git
negeert exclude-regels voor tracked bestanden, ripgrep niet). Dat is op 2026-08-01
opgeschoond. Deze test gebruikt bewust `Path.rglob`, dat geen ignore-regels leest en die
blinde vlek dus niet heeft.
"""

import ast
from pathlib import Path

SRC_ROOT = Path("src")

# Klassenamen waarvan een tweede definitie verwarrend genoeg is om te blokkeren.
WATCHED_NAMES = {
    "ToolPermissionManager",
    "ToolCategory",
    "PermissionEffect",
    "PermissionDeniedError",
}

# Bekende, geaccepteerde meervoudige definities. Leeg sinds OP-15 is opgelost
# (2026-08-01). Een nieuwe regel hier hoort een datum en een reden te krijgen.
KNOWN_COLLISIONS: dict[str, set[str]] = {}


def _class_definitions() -> tuple[dict[str, set[str]], list[str], int]:
    """({klassenaam: {bestandspaden}} voor elke bewaakte naam, parse-fouten, aantal gescand)."""
    found: dict[str, set[str]] = {}
    fouten: list[str] = []
    gescand = 0
    for path in sorted(SRC_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            fouten.append(f"{path.as_posix()}: {exc}")
            continue
        gescand += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in WATCHED_NAMES:
                found.setdefault(node.name, set()).add(path.as_posix())
    return found, fouten, gescand


def test_no_permission_class_name_is_defined_twice() -> None:
    """Geen bewaakte permissie-naam mag op twee plekken gedefinieerd zijn."""
    actual, _fouten, _gescand = _class_definitions()
    violations: list[str] = []

    for name, paths in sorted(actual.items()):
        known = KNOWN_COLLISIONS.get(name, set())
        unexpected = paths - known
        if len(paths) > 1 or (known and unexpected):
            violations.append(f"{name}: {sorted(paths)}")

    assert not violations, (
        "Twee klassen met dezelfde naam die verschillende dingen doen is precies de "
        "verwarring die bij de drie ChiefOrchestrator-klassen al tot fouten leidde "
        "(ADR-036 par. 1.2.B). Hernoem de nieuwe, of voeg hem met datum en reden toe aan "
        "KNOWN_COLLISIONS als het echt niet anders kan:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_the_scan_actually_scans_files() -> None:
    """Vangnet: een onleesbaar/onparseerbaar bestand mag de botsingscontrole niet blind maken.

    Krijgt het EERSTE bestand dat een bewaakte naam definieert een BOM of syntaxfout terwijl
    ELDERS een botsende klasse verschijnt, dan blijft er nog precies EEN vindplaats over per
    naam en ziet de test hierboven de botsing nooit -- ook al is dat de hele reden waarom
    OP-15 destijds is opgelost.
    """
    _, fouten, gescand = _class_definitions()
    assert gescand >= 1500, (
        f"Slechts {gescand} bestanden gescand onder {SRC_ROOT} -- dat lijkt een (bijna) "
        "lege boom. Deze guard controleert dan vrijwel niets."
    )
    assert not fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden en zijn NIET gecontroleerd op "
        "een botsende klassenaam:\n" + "\n".join(f"  - {f}" for f in fouten)
    )


def test_known_collisions_are_not_stale() -> None:
    """Een uitzondering die niet meer bestaat moet uit de lijst -- anders rot hij dicht."""
    actual, _fouten, _gescand = _class_definitions()
    stale: list[str] = []

    for name, known_paths in KNOWN_COLLISIONS.items():
        for path in known_paths:
            if not Path(path).exists():
                stale.append(f"{name}: {path} bestaat niet meer")
            elif path not in actual.get(name, set()):
                stale.append(f"{name}: {path} definieert die klasse niet meer")

    assert not stale, "KNOWN_COLLISIONS is verouderd -- haal deze regels weg:\n" + "\n".join(
        f"  - {s}" for s in stale
    )


def test_the_active_manager_is_the_yaml_one() -> None:
    """Vastleggen WELKE klasse het echte permissiepad bedient.

    Zonder deze test is bij een volgende wijziging niet af te lezen welke manager de broker
    aanstuurt -- en dan is de kans reeel dat iemand een tweede permissiemodel bouwt in de
    veronderstelling dat dat het levende is. Dat is exact hoe OP-15 is ontstaan.
    """
    service = Path("src/core/tool_broker/service.py").read_text(encoding="utf-8")
    assert "from src.core.tool_broker.permission_manager import ToolPermissionManager" in service, (
        "ToolBrokerService moet de YAML-gebaseerde ToolPermissionManager gebruiken "
        "(tool_broker/permission_manager.py)."
    )

    assert not Path("src/core/agents/tool_permissions.py").exists(), (
        "src/core/agents/tool_permissions.py is op 2026-08-01 verwijderd (OP-15). Komt hij "
        "terug, dan is het naamconflict terug -- kies dan een naam die niet botst met de "
        "levende permissielaag, bijvoorbeeld CategoryToolPermissionManager."
    )
