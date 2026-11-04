"""Een opgeloste doc-gate-uitzondering MOET van de lijst af (ADR-036 OP-180 nazorg).

**Waarom deze test bestaat.** `docs/backend/features/DOC-GATE-EXCEPTIONS.md` maakt de doc-poort
groen op bekende, gedateerde gevallen. Dat mechanisme is nodig -- een poort die permanent rood
staat leest niemand meer -- maar het heeft een weesrisico dat op 2026-09-01 expliciet is
benoemd: wordt de onderliggende fix gemerged en vergeet iemand de regel te verwijderen, dan is
dat ID vanaf dat moment PERMANENT ge-whitelist. Elke latere regressie op dat ID glipt er
stilzwijgend door.

**Waarom de bestaande melding niet volstaat.** De validator MELDT dit al wel:
`scripts/validate_feature_docs.py:262-271` zet een compleet-maar-nog-uitgezonderd ID op
`[PENDING-RESOLVED]` met het verzoek de regel te verwijderen. Gemeten dat die code echt bestaat
en niet alleen in de documentatie staat. Maar het is een waarschuwing in de uitvoer van een run
die exitcode 0 geeft, en de uitvoer van een groene run leest niemand. Vandaar deze test ernaast.

**Waarom het een TEST is en niet een harde fout in de poort zelf.** Regel 3 van het
uitzonderingsbestand zegt: "De gate blijft groen -- documentatie verbeteren mag nooit een merge
blokkeren." Die regel is juist, en daarom blokkeert deze test het VERBETEREN niet: hij faalt
alleen op het LATEN STAAN van een uitzondering die niet meer nodig is. Zelfde vorm als de
gedateerde-uitzondering-met-staleness-test uit `.claude/rules/quality-gates.md`.

**Hergebruik, geen namaak.** De vraag "is dit ID compleet?" wordt beantwoord door
`check_entry()` uit de validator zelf. Een eigen tweede definitie van compleetheid zou gaan
afwijken, en dan bewaakt deze test iets anders dan de poort.

**Mutatiebewijs -- uitgevoerd en gemeten 2026-09-01, beide richtingen.** Terugweg via een kopie,
nooit `git checkout --`:

- ongemuteerd, met BE-AGT-045/BE-AGT-062/BE-SEC-048 uitgezonderd en incompleet:
  verwacht GROEN, gemeten `1 passed`;
- BE-SEC-048 compleet gemaakt (een `## Trainingssamenvatting` met een `- Actor:`-flow plus
  een APPROVED-review) terwijl de uitzonderingsregel blijft staan: verwacht ROOD, gemeten
  `1 failed`;
- dezelfde documenten weer incompleet, uitzondering blijft staan: verwacht GROEN, gemeten
  `1 passed`.

Na herstel is de spec byte-identiek gecontroleerd met `diff -q`, is het wegwerp-reviewbestand
verwijderd, en geeft de poort weer exitcode 0. Dat wegwerp-review droeg met opzet `APPROVED`; het
is nooit gecommit, want een valse goedkeuring in de audit trail is erger dan een rode poort -- en
dat is precies de reden dat BE-SEC-048 hier uitgezonderd staat in plaats van half opgelost.

Het derde geval is de dragende tegenrichting: zonder die meting zou "faal altijd" een geldige
implementatie zijn, en dan zou de uitzonderingslijst onbruikbaar worden voor het doel waarvoor
hij bestaat.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _validator_functies() -> tuple[object, object, object, dict[str, object]]:
    """De drie functies plus de prefix-configuratie uit de validator zelf.

    LET OP, en dit is in twee stappen gemeten en niet bedacht.
    `scripts/validate_feature_docs.py` vervangt op MODULENIVEAU `sys.stdout` en `sys.stderr`
    door `io.TextIOWrapper(sys.stdout.buffer, ...)` (regel 9-11, voor UTF-8-uitvoer op Windows).

    Poging 1, kale import: `1 failed, 3 errors`, met de stacktrace in pytest's eigen
    `_ensure_unconfigure` en niet in de test.

    Poging 2, de streams eromheen bewaren en terugzetten: NOG STEEDS rood, met
    `ValueError: I/O operation on closed file`. Terugzetten is niet genoeg, want de wrapper
    heeft dan al de BUFFER van pytest's capture in bezit en sluit die bij opruiming.

    Wat wel werkt: `sys.stdout` en `sys.stderr` VOOR de import naar een wegwerpbuffer wijzen.
    De validator wrapt dan die wegwerpbuffer, en wat hij sluit is niemands eigendom. Zelfde
    familie als het module-level neveneffect dat een verse testboom laat omvallen (een
    ChromaDB-client die bij IMPORT een opslag aanmaakt) -- en een concrete prijs voor werk
    op moduleniveau dat in een functie had gehoord. Het OP-nummer daarvan staat bewust niet
    hier: die registerrij leeft nog op `merge/golf1` en niet op `develop`, en een
    verwijzing naar een rij die hier niet bestaat is precies wat OP-181 verbiedt. Deze
    docstring is er zelf op betrapt door die guard.
    """
    bewaard_out, bewaard_err = sys.stdout, sys.stderr
    try:
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from validate_feature_docs import (  # noqa: PLC0415
            CONFIG,
            check_entry,
            load_exceptions,
            parse_registry,
        )
    finally:
        sys.stdout, sys.stderr = bewaard_out, bewaard_err

    return load_exceptions, parse_registry, check_entry, CONFIG


def _alle_regels() -> list[dict[str, object]]:
    _, parse_registry, _, CONFIG = _validator_functies()
    regels: list[dict[str, object]] = []
    for prefix in CONFIG:
        regels.extend(parse_registry(prefix))  # type: ignore[operator]
    return regels


@pytest.mark.unit
def test_the_scan_finds_exceptions_and_registry_rows() -> None:
    """Vangnet: zonder uitzonderingen of zonder registerregels bewaakt deze test niets.

    Rood te maken door de sectie `## Openstaand` uit het uitzonderingsbestand te halen, of door
    `parse_registry` een lege lijst te laten geven.
    """
    load_exceptions, _, _, CONFIG = _validator_functies()
    uitzonderingen = load_exceptions()  # type: ignore[operator]
    regels = _alle_regels()

    assert uitzonderingen, (
        "Nul uitzonderingen gelezen uit docs/backend/features/DOC-GATE-EXCEPTIONS.md. Als de "
        "lijst werkelijk leeg is, mag deze test weg -- maar controleer eerst of het parsen nog "
        "werkt, want een leeg resultaat maakt de staleness-toets hieronder betekenisloos."
    )
    assert len(regels) > 100, (
        f"Slechts {len(regels)} registerregels gelezen over {len(CONFIG)} prefixen. Gemeten "
        "2026-09-01: 699. Is het registerformaat gewijzigd, dan meet deze test niets meer."
    )


@pytest.mark.unit
def test_no_resolved_exception_stays_on_the_list() -> None:
    """DE toets: een ID dat compleet is, mag niet meer uitgezonderd staan.

    Rood te maken door de ontbrekende documentatie voor een uitgezonderd ID te schrijven en de
    regel in `DOC-GATE-EXCEPTIONS.md` te laten staan. Dat is precies het scenario dat bij de
    `merge/golf1`-merge dreigt: de fix landt, de uitzondering blijft.
    """
    load_exceptions, _, check_entry, _ = _validator_functies()
    uitzonderingen = load_exceptions()  # type: ignore[operator]

    verlopen: list[str] = []
    gezien: set[str] = set()
    for regel in _alle_regels():
        sleutel = f"{regel['prefix']}:{regel['file']}"
        if sleutel in gezien:
            continue
        gezien.add(sleutel)
        if regel["id"] in uitzonderingen and not check_entry(regel):  # type: ignore[operator]
            verlopen.append(str(regel["id"]))

    assert not verlopen, (
        "Deze IDs staan op de uitzonderingslijst maar zijn nu volledig gedocumenteerd: "
        f"{sorted(verlopen)}.\n"
        "Haal ze uit docs/backend/features/DOC-GATE-EXCEPTIONS.md (verplaats ze naar de sectie "
        "'Opgelost (historie)'). Zolang ze blijven staan, is dat ID PERMANENT ge-whitelist en "
        "glipt elke latere regressie erop stilzwijgend door de poort. Dat is het weesrisico "
        "waarvoor deze test bestaat."
    )
