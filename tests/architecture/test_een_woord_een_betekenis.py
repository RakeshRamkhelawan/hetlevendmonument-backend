"""Het kale woord "poort" staat niet in een levend instructiebestand.

**Waarom deze guard bestaat (gemeten 2026-09-17).** Het woord "poort" betekende in de
instructiebestanden ZES verschillende dingen: een genummerde netwerkingang, de blokkerende
testronde, de drie handboekcontroles, de council-gate, de documentatiecontrole, en de
push-goedkeuring. Twee daarvan stonden in CLAUDE.md twaalf regels uit elkaar.

Wat dat kostte: een sessie draaide het voorgeschreven testcommando, kreeg groen, en zag
haar push daarna geweigerd. Beide heetten "de poort", dus leek dezelfde controle twee
antwoorden te geven -- wat niet kan, dus werd de fout op de verkeerde plek gezocht. Een
dag kwijt. Er was geen foutmelding en geen rode test, alleen twee getallen (16595 en 16599)
en een woord dat suggereerde dat het om hetzelfde ging.

Voor een AI weegt dit zwaarder dan voor een mens. Een mens leidt de betekenis af uit de
context; een agent leest de naam letterlijk en behandelt een naam als een hard signaal.
Achtergrond: Ubiquitous Language (een term, een betekenis, vastgelegd in een woordenlijst
die iedereen leest) en de Google developer documentation style guide, die expliciet stelt
dat hetzelfde woord nooit twee begrippen mag aanduiden.

**Bereik: precies deze vier bestanden, expliciet genoemd.** Niet "alles wat op .md
eindigt". `docs/agent-briefs/generated/` valt er bewust BUITEN: dat zijn verslagen van wat
er destijds stond, geen instructies, en meeveranderen zou een verslag onwaar maken.

**De valkuil die deze guard zelf bijna opat.** Het woord "poort" zit IN de oplossing
(testpoort, netwerkpoort, kwaliteitspoort). Een zoektocht op de letters betrapt dus zijn
eigen antwoord -- dezelfde vorm als een filter dat ooit op een bestandsnaam matchte in
plaats van op een pad en toen ten onrechte "geen aanroeper" concludeerde. Daarom matcht
`_KAAL_WOORD` op het woord ALS woord: geen letter en geen koppelteken ervoor of erna.

Mutatiebewijs (2026-09-17), een regel per bewaakt bestand en in beide richtingen, met een
kopie als terugweg en nooit via `git checkout`:

    kaal "poort" in CLAUDE.md                 -> ROOD
    kaal "poort" in WORKING-CONTEXT.md        -> ROOD
    kaal "poort" in quality-gates.md          -> ROOD
    kaal "poort" in scripts/hooks/pre-push    -> ROOD
    de samenstelling "testpoort" toegevoegd   -> GROEN  (anders verbiedt hij de oplossing)
    een rij uit de woordenlijst verwijderd    -> ROOD
    alles hersteld                            -> GROEN
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: De LEVENDE instructiebestanden. Expliciet genoemd zodat het mutatiebewijs een regel per
#: bestand kan hebben, en zodat niemand per ongeluk de historische briefs meeneemt.
INSTRUCTIEBESTANDEN = (
    "CLAUDE.md",
    ".claude/WORKING-CONTEXT.md",
    ".claude/rules/quality-gates.md",
    "scripts/hooks/pre-push",
)

#: De samenstellingen die de betekenis WEL benoemen. Staat hier zodat een nieuwe
#: samenstelling een bewuste toevoeging is en geen stille uitbreiding.
TOEGESTANE_SAMENSTELLINGEN = (
    "netwerkpoort",
    "testpoort",
    "kwaliteitspoort",
    "bestuurspoort",
    "documentatiepoort",
)

#: Het woord ALS woord. De grenzen sluiten drie dingen uit die GEEN dubbelzinnig gebruik
#: zijn, alle drie gemeten tijdens het bouwen van deze guard:
#:   - een letter of koppelteken ervoor/erna -> een samenstelling (testpoort, netwerkpoort);
#:     zonder deze grens betrapt de guard zijn eigen oplossing;
#:   - een underscore of punt -> een bestands- of functienaam
#:     (test_de_voorgeschreven_poort_is_de_afgedwongen_poort.py is geen proza).
_KAAL_WOORD = re.compile(r"(?<![A-Za-z._-])poort(en)?(?![A-Za-z._-])", re.IGNORECASE)

#: De sectie die de regel ZELF definieert mag het woord noemen -- je kunt een woord niet
#: verbieden zonder het te schrijven. Bereik: vanaf de kop tot de eerstvolgende `---`.
_WOORDENLIJST_KOP = "## Woordenlijst"


def _zonder_woordenlijst(regels: list[str], pad: Path) -> list[tuple[int, str]]:
    """Nummer elke regel, maar laat de woordenlijst-sectie van CLAUDE.md weg."""
    genummerd = list(enumerate(regels, start=1))
    if pad.name != "CLAUDE.md":
        return genummerd
    start = next((i for i, r in genummerd if r.startswith(_WOORDENLIJST_KOP)), None)
    assert start is not None, (
        "De woordenlijst-sectie ontbreekt in CLAUDE.md. Die legt uit WAAROM het kale woord "
        "verboden is; zonder die uitleg is deze guard een regel zonder reden."
    )
    eind = next((i for i, r in genummerd if i > start and r.strip() == "---"), None)
    assert eind is not None, "De woordenlijst-sectie heeft geen afsluitende `---`."
    return [(i, r) for i, r in genummerd if not start <= i <= eind]


def _regels_met_kaal_woord(pad: Path) -> list[tuple[int, str]]:
    regels = pad.read_text(encoding="utf-8").splitlines()
    return [
        (nr, regel.strip())
        for nr, regel in _zonder_woordenlijst(regels, pad)
        if _KAAL_WOORD.search(regel)
    ]


def test_geen_kaal_woord_poort_in_een_instructiebestand() -> None:
    """Elke vermelding zegt WELKE poort, anders is hij dubbelzinnig."""
    treffers: list[str] = []
    for relatief in INSTRUCTIEBESTANDEN:
        pad = REPO_ROOT / relatief
        assert pad.is_file(), (
            f"{relatief} bestaat niet. Deze guard meet dan minder dan hij belooft terwijl "
            "hij groen meldt -- dat is een fout en geen overslaan. Hernoemd of verplaatst? "
            "Werk INSTRUCTIEBESTANDEN bij."
        )
        for nr, regel in _regels_met_kaal_woord(pad):
            treffers.append(f"  {relatief}:{nr}  {regel[:110]}")

    assert not treffers, (
        "Het kale woord 'poort' staat in een instructiebestand. Het betekent in dit project "
        "zes verschillende dingen; schrijf welke je bedoelt:\n"
        + "    "
        + ", ".join(TOEGESTANE_SAMENSTELLINGEN)
        + ", of pushgoedkeuring\n"
        + "Gevonden:\n"
        + "\n".join(treffers)
        + "\n"
        "Zie de woordenlijst bovenaan CLAUDE.md. Op 2026-09-17 kostte deze dubbelzinnigheid "
        "een dag: twee sessies vergeleken 16595 met 16599 zonder te zien dat het twee "
        "verschillende testrondes waren."
    )


def test_de_woordenlijst_legt_elke_samenstelling_uit() -> None:
    """Een nieuw woord zonder uitleg is alleen een nieuw raadsel."""
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    ontbreekt = [
        woord
        for woord in (*TOEGESTANE_SAMENSTELLINGEN, "pushgoedkeuring")
        if f"`{woord}`" not in claude_md
    ]
    assert not ontbreekt, (
        f"Deze woorden staan niet in de woordenlijst van CLAUDE.md: {ontbreekt}. "
        "Wie ze tegenkomt kan nergens opzoeken wat ze betekenen, en dan is er niets "
        "opgelost -- alleen een onbekend woord in de plaats van een dubbelzinnig woord."
    )
