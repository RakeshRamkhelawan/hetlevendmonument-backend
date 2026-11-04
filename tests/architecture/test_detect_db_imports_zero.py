"""Architecture test: detect_db_imports CI-gate -- AUDIT-DB01 S6.

Alle 13 domeinen moeten ADR-033 service-laag gebruiken.
detect_db_imports.py MOET exit code 0 retourneren -- behalve de gedateerde
uitzondering hieronder (OP-204, Fase D).

**OP-204, 2026-09-04.** Deze poort stond drie maanden ONBEDOELD groen: een
byte-order-mark in `src/core/api/v1/agent_configs/router.py` gaf de scanner
`ast.parse()` een `SyntaxError`, en `scan_file()` vangt die stil op met
`return []` (zie OP-203 voor het mechanisme). Na het weghalen van de BOM
(commit `257e120a`) bleek dit bestand al sinds v66r de facade-migratie
(`from src.core.api.dependencies import get_db`) toch nog een ruwe
`AsyncSession`/`get_db`-databanksessie in de router zelf gebruikt -- de
scanner verbiedt deze NAMEN letterlijk, ongeacht via welke module ze
binnenkomen of onder welke alias (`alias.name`, niet de lokale binding), dus
een voordeur-verplaatsing lost dit principieel niet op. De echte fix is de
6 route-handlers in dat bestand herschrijven zodat ze de databanksessie niet
meer als parameter aannemen (delegeren aan een service/repository-laag) --
dat is een gedragswijziging in productiecode en hoort een eigen wijziging met
een eigen Gate 2 te zijn, niet deze BOM-opruiming.
"""

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent


class _KnownOffender:
    """Een gedateerde uitzondering: reden + de PRECIEZE overtredingen die hij dekt.

    Gate-2-bevinding (2026-09-04, security-reviewer): een lijst die alleen op
    bestandsnaam matcht, is blind voor een NIEUWE overtredingssoort in een al
    uitgezonderd bestand. Aangetoond door te simuleren dat hetzelfde bestand
    ineens ook `text` (raw-SQL) rapporteert -- beide tests bleven groen. Door
    de exacte verzameling namen vast te leggen en die te vergelijken (niet
    alleen de bestandsnaam), forceert een NIEUWE naam in hetzelfde bestand nu
    wel een nieuwe, gedateerde regel.
    """

    def __init__(self, reason: str, forbidden_imports: frozenset[str]) -> None:
        self.reason = reason
        self.forbidden_imports = forbidden_imports


#: Gemeten 2026-09-04, `python scripts/detect_db_imports.py`. Reden + exacte
#: overtredingen per regel.
KNOWN_DB_IMPORT_OFFENDERS: dict[str, _KnownOffender] = {
    "src/core/api/v1/agent_configs/router.py": _KnownOffender(
        reason=(
            "ruwe AsyncSession/get_db-parameter in 6 route-handlers -- OP-204, Fase D, "
            "pending Strangler Fig service-laag migratie (zelfde markering als de "
            "orphan:exempt-comment bovenaan het bestand)"
        ),
        forbidden_imports=frozenset({"AsyncSession", "get_db"}),
    ),
}


def _run_scanner() -> dict:
    result = subprocess.run(
        [sys.executable, "scripts/detect_db_imports.py"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    return json.loads(result.stdout)


def test_no_new_db_import_offenders() -> None:
    """CI-gate: geen NIEUWE router-bestanden EN geen NIEUWE overtredingssoort
    in een al uitgezonderd bestand.

    Rood te maken door (a) een databanksessie-parameter aan een ANDER
    router-bestand toe te voegen dan die in KNOWN_DB_IMPORT_OFFENDERS staat, of
    (b) een bestaand uitgezonderd bestand een AANVULLENDE verboden import te
    geven (bijv. `text` naast `AsyncSession`/`get_db`) die niet in zijn
    `forbidden_imports` staat.
    """
    report = _run_scanner()
    reported = {o["file"]: frozenset(o["forbidden_imports"]) for o in report["offenders"]}

    nieuwe_bestanden = set(reported) - set(KNOWN_DB_IMPORT_OFFENDERS)
    assert not nieuwe_bestanden, (
        f"Nieuwe ADR-033-violations in router-bestanden zonder gedateerde reden: "
        f"{sorted(nieuwe_bestanden)}. Run: python scripts/detect_db_imports.py"
    )

    onverwacht: dict[str, frozenset[str]] = {}
    for bestand, gevonden in reported.items():
        known = KNOWN_DB_IMPORT_OFFENDERS.get(bestand)
        if known is None:
            continue
        extra = gevonden - known.forbidden_imports
        if extra:
            onverwacht[bestand] = extra
    assert not onverwacht, (
        f"Bestaande uitzonderingen hebben een NIEUWE overtredingssoort die niet gedateerd "
        f"is: {onverwacht}. Breid KNOWN_DB_IMPORT_OFFENDERS['<bestand>'].forbidden_imports "
        f"uit met een eigen reden, of fix de nieuwe overtreding."
    )


def test_known_db_import_offenders_are_not_stale() -> None:
    """Wie een uitzondering repareert, MOET de regel uit de lijst halen.

    Rood te maken door een bestand in KNOWN_DB_IMPORT_OFFENDERS te zetten dat NIET
    meer als offender gerapporteerd wordt, of door een `forbidden_imports`-naam op
    te nemen die niet meer voorkomt.
    """
    report = _run_scanner()
    reported = {o["file"]: frozenset(o["forbidden_imports"]) for o in report["offenders"]}

    opgelost = [f for f in KNOWN_DB_IMPORT_OFFENDERS if f not in reported]
    assert not opgelost, (
        "Mooi werk -- deze bestanden gebruiken geen ruwe databanksessie meer. Haal ze uit "
        f"KNOWN_DB_IMPORT_OFFENDERS in DEZELFDE commit: {sorted(opgelost)}"
    )

    verouderde_namen: dict[str, frozenset[str]] = {}
    for bestand, known in KNOWN_DB_IMPORT_OFFENDERS.items():
        gevonden = reported.get(bestand, frozenset())
        verdwenen = known.forbidden_imports - gevonden
        if verdwenen:
            verouderde_namen[bestand] = verdwenen
    assert not verouderde_namen, (
        "Mooi werk -- deze specifieke overtredingen komen niet meer voor. Verklein "
        f"forbidden_imports in KNOWN_DB_IMPORT_OFFENDERS in DEZELFDE commit: {verouderde_namen}"
    )


def test_detect_db_imports_script_exists() -> None:
    """CI-gate: scripts/detect_db_imports.py moet aanwezig zijn."""
    script = _REPO_ROOT / "scripts" / "detect_db_imports.py"
    assert script.exists(), (
        "scripts/detect_db_imports.py ontbreekt -- S6 CI-gate vereist dit script"
    )
