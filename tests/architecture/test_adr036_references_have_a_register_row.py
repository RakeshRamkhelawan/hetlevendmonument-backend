"""Code mag niet verwijzen naar een ADR-036-registerrij die niet bestaat (OP-181).

**De bevinding.** Op 2026-09-01 verwezen productiecode en architecture-tests naar OP-75, OP-76 en
OP-77 alsof dat registerrijen waren. Ze bestonden niet: tussen OP-74 en OP-78 zat een gat in de
tabel. `src/core/api/v1/tool_broker/hitl_router.py`, `src/workers/scheduler.py`,
`src/core/tool_broker/redaction.py` en vier testbestanden noemden die nummers, en een lezer die de
rij ging opzoeken vond niets en concludeerde dat hij zelf iets miste.

Diezelfde week gebeurde het opnieuw en toen als NIEUWE fout: de OP-03-workstream schreef OP-178 in
zes OpenAPI-beschrijvingen en in een guard-docstring voordat de rij bestond. Een onafhankelijke
reviewer betrapte dat. Twee instanties van hetzelfde patroon binnen een week, en de tweede was er
een die ik zelf maakte -- dat is de definitie van iets dat een guard hoort te zijn en geen
gewoonte.

**Waarom dit erger is dan een ontbrekende toelichting.** Het register is de plek waar dit project
zijn openstaande punten bijhoudt, met status, verificatiedatum en machinaal controleerbaar bewijs
per rij (`test_adr036_register_is_parseable.py`). Een verwijzing naar een niet-bestaande rij
belooft die hele administratie en levert niets. En hij is stil: niets faalt, de code compileert,
de tests draaien.

**Wat deze guard NIET doet.** Hij toetst niet of de rij het juiste ZEGT -- alleen dat hij bestaat.
De inhoud is het werkterrein van `test_adr036_register_is_parseable.py`, dat status, datum en
bewijs per rij afdwingt. Samen dekken ze de twee helften: bestaat de rij, en zegt hij iets
controleerbaars.

**De linker woordgrens is niet cosmetisch, en dat is gemeten.** Een kale `OP-\\d+` matcht ook
binnen langere tekens: `SKU-LAPTOP-001` levert `OP-001` op en `RC-LOOP-1` levert `OP-1` op. Dat
zijn de twee enige valse positieven in de hele repo (gemeten 2026-09-01) en beide staan hieronder
als GROEN-geval in de mutatietabel. Zonder die grens zou deze guard op dag een rood staan om twee
redenen die niets met het register te maken hebben -- en een guard die om de verkeerde reden rood
staat, wordt uitgezet.

**Mutatiebewijs -- een regel per vorm, beide richtingen** (`_REGEL_GEVALLEN` plus
`test_the_rule_itself_catches_every_known_form`, dat de mutaties bij elke run uitvoert in plaats
van ze in proza te beschrijven). Verplicht ROOD:

- een verwijzing naar een nummer boven het hoogste bestaande rijnummer;
- een verwijzing naar een nummer in een gat tussen bestaande rijen;
- de vorm met het ADR-nummer ervoor (`ADR-036 OP-999`);
- een verwijzing in een comment, want juist daar staan ze in dit project.

Verplicht GROEN (zonder deze helft is "meld nooit iets" en ook "meld alles" een geldige
implementatie):

- een verwijzing naar een nummer dat WEL een rij heeft;
- `SKU-LAPTOP-001` (gemeten valse positief zonder de linker woordgrens);
- `RC-LOOP-1` (idem);
- een nummer met voorloopnullen dat nergens als rij bestaat maar ook geen verwijzing IS
  (`ORDER-0001`).

**Mutatiebewijs op ECHTE inhoud, uitgevoerd en gemeten 2026-09-01** (naast de synthetische
gevallen hierboven, die bij elke run meedraaien). Terugweg via een kopie, nooit `git checkout --`;
na herstel zijn beide bestanden byte-identiek gecontroleerd met `diff -q`:

| Mutatie | Verwacht | Gemeten |
| --- | --- | --- |
| ongemuteerd | GROEN | 1 passed |
| de rij `OP-75` uit de registertabel gehaald (code citeert dat nummer 9x) | ROOD | 1 failed |
| `# ... (ADR-036 OP-997).` toegevoegd aan `src/core/shared/public_registry.py` | ROOD | 1 failed |
| LEGITIEM: `# ... (ADR-036 OP-182).` toegevoegd aan datzelfde bestand | GROEN | 1 passed |
| na herstel | GROEN | 1 passed |

De vierde regel is de dragende tegenrichting: zonder die meting zou "meld elke OP-verwijzing" een
geldige implementatie zijn en zou deze guard onbruikbaar worden zodra iemand een rij correct
citeert.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: De mappen waarin een OP-verwijzing een claim over het register is. `docs/` staat er bewust
#: NIET bij: daar staan rapporten en briefs die over historische nummeringen schrijven, en die
#: mogen een nummer noemen dat later is herzien.
#:
#: `frontend` toegevoegd 2026-09-01 na een gemeten blinde vlek: frontend-code citeert wel
#: OP-nummers (9 unieke over 8 bestanden, o.a. `App.tsx` en `hooks/useHITL.ts`) en viel
#: buiten deze verzameling. Nul daarvan bleek zwevend, dus toevoegen kon zonder iets te
#: repareren -- maar zonder deze regel was een volgende frontend-verwijzing onbewaakt.
SCAN_ROOTS = ("src", "tests", "scripts", ".github", "frontend")

#: Precies EEN bestand is uitgezonderd: dit bestand zelf. De OP-nummers hierin zijn INVOER voor
#: de regel (de synthetische mutatiegevallen `OP-901` tot `OP-904`, en de twee gemeten valse
#: positieven `SKU-LAPTOP-001` en `RC-LOOP-1`) en geen verwijzingen naar het register. Zonder
#: deze uitzondering meldt de guard zijn eigen testdata -- gemeten toen dit bestand voor het
#: eerst getrackt werd: vijf "zwevende" nummers, alle vijf uit de tabel hieronder en uit de
#: moduledocstring.
#:
#: Deze lijst mag NIET groeien. Een tweede bestand hierin betekent dat iemand een echte
#: verwijzing wil uitzonderen in plaats van de rij te schrijven, en dat is precies wat OP-181
#: onmogelijk moet maken. `test_the_exclusion_covers_only_this_file` dwingt dat af.
EXCLUDED_FROM_SCAN = ("tests/architecture/test_adr036_references_have_a_register_row.py",)

#: De linker grens sluit `SKU-LAPTOP-001` en `RC-LOOP-1` uit. Zie de moduledocstring: dat zijn
#: de twee gemeten valse positieven, en zonder deze grens staat de guard om de verkeerde reden
#: rood.
REFERENCE = re.compile(r"(?<![A-Za-z0-9-])OP-\d+")

#: Rijen in de registertabel van ADR-036.
ROW = re.compile(r"^\| (OP-\d+) \|", re.M)


def _register_paths() -> list[Path]:
    """De registerbestanden. Sinds 2026-09-19 zijn het er TWEE.

    Tot die datum stond hier `assert len(paden) == 1`. Het register is op instructie van
    Rakesh gesplitst: ADR-036 houdt zijn eigen open rijen, al het afgeronde werk en alles wat
    niet over de agentlaag gaat staat in `036-REGISTER-OVERIG-EN-AFGEROND.md`. Een verwijzing
    in code moet in EEN van beide een rij hebben -- welke van de twee doet er voor deze guard
    niet toe, want hij bewaakt of de rij BESTAAT en niet waar hij woont.

    De classificatiebijlage (`036-SPLITSING-CLASSIFICATIE.md`) bevat geen registerrijen en
    wordt daarom overgeslagen; hij zou anders als derde register meetellen.
    """
    paden = [
        pad
        for pad in sorted((REPO_ROOT / "docs" / "adr").glob("036-*.md"))
        if "SPLITSING-CLASSIFICATIE" not in pad.name
    ]
    assert len(paden) == 2, f"verwacht twee ADR-036-registerbestanden, gevonden: {paden}"
    return paden


def _register_rows() -> set[str]:
    rijen: set[str] = set()
    for pad in _register_paths():
        rijen.update(ROW.findall(pad.read_text(encoding="utf-8")))
    return rijen


def _references_in_code() -> dict[str, list[str]]:
    """Verwijzing -> de regels waar hij staat. Via `git grep`, dus alleen GETRACKTE bestanden.

    Waarom `git grep` en niet een eigen boomwandeling: `.gitignore` van dit project verborg
    eerder 1816 getrackte bestanden voor ripgrep-achtig gereedschap, en een guard die zijn eigen
    zoekbereik niet kan verantwoorden meet niets. `git grep` leest de index en heeft dat
    probleem niet.
    """
    resultaat = subprocess.run(
        ["git", "grep", "-nE", r"OP-[0-9]+", "--", *SCAN_ROOTS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        errors="replace",
    )
    # returncode 1 betekent bij git grep "niets gevonden" en is geen fout; 2 en hoger wel.
    assert resultaat.returncode in (0, 1), (
        f"git grep faalde met returncode {resultaat.returncode}: {resultaat.stderr.strip()}. "
        "Een genegeerde returncode heeft in dit project eerder een guard groen gehouden op een "
        "lege uitvoer."
    )
    gevonden: dict[str, list[str]] = {}
    for regel in resultaat.stdout.splitlines():
        pad = regel.split(":", 1)[0].replace("\\", "/")
        if pad in EXCLUDED_FROM_SCAN:
            continue
        for nummer in dict.fromkeys(REFERENCE.findall(regel)):
            gevonden.setdefault(nummer, []).append(regel)
    return gevonden


#: Elk geval is een bronregel met het aantal verwijzingen dat de REGEL eruit moet halen. De
#: nummers 900 en hoger bestaan met opzet niet als rij; 75 en 178 wel.
_REGEL_GEVALLEN: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "verwijzing boven het hoogste rijnummer",
        'DESCRIPTION = "weigert in plaats van te liegen (ADR-036 OP-999)."',
        ("OP-999",),
    ),
    (
        "verwijzing in een gat tussen bestaande rijen",
        "# De poort draait hier bewust niet (ADR-036 OP-901).",
        ("OP-901",),
    ),
    (
        "vorm zonder het ADR-nummer ervoor",
        '    """Zie OP-902 voor de meting."""',
        ("OP-902",),
    ),
    (
        "twee verwijzingen op een regel",
        "# Zelfde familie als OP-903 en OP-904.",
        ("OP-903", "OP-904"),
    ),
    (
        "LEGITIEM: bestaande rij",
        "# De eenmaligheid uit OP-63/OP-75 hing aan iets dat mag falen.",
        ("OP-63", "OP-75"),
    ),
    (
        "LEGITIEM: SKU-LAPTOP-001 is geen verwijzing",
        '    OrderItem("SKU-LAPTOP-001", "Laptop Pro", 2, "A-01")',
        (),
    ),
    (
        "LEGITIEM: RC-LOOP-1 is geen verwijzing",
        "# RC-LOOP-1: Force SelectorEventLoop on Windows",
        (),
    ),
    (
        "LEGITIEM: ORDER-0001 is geen verwijzing",
        '    ref = "ORDER-0001"',
        (),
    ),
)


@pytest.mark.architecture
@pytest.mark.parametrize(("omschrijving", "regel", "verwacht"), _REGEL_GEVALLEN)
def test_the_rule_itself_catches_every_known_form(
    omschrijving: str, regel: str, verwacht: tuple[str, ...]
) -> None:
    """De REGEL wordt gemuteerd op synthetische regels, niet de productiecode.

    De ROOD-helft toetst de detectie, de GROEN-helft sluit uit dat de regel alles vlagt. De twee
    valse positieven (`SKU-LAPTOP-001`, `RC-LOOP-1`) zijn geen bedachte gevallen: ze staan
    letterlijk in deze repo en waren de enige twee treffers die de linker woordgrens nodig hadden.
    """
    gevonden = tuple(dict.fromkeys(REFERENCE.findall(regel)))
    assert gevonden == verwacht, (
        f"{omschrijving}: de regel haalt {gevonden} uit deze bronregel, verwacht {verwacht}."
    )


@pytest.mark.architecture
def test_the_scan_finds_references_at_all() -> None:
    """Vangnet: zonder gevonden verwijzingen bewaakt deze guard niets.

    Rood te maken door `SCAN_ROOTS` leeg te zetten of door de scan naar een lege map te richten.
    """
    gevonden = _references_in_code()
    assert len(gevonden) >= 50, (
        f"Slechts {len(gevonden)} unieke OP-verwijzingen gevonden in {SCAN_ROOTS}. Dat is te "
        "weinig om geloofwaardig te zijn -- gemeten 2026-09-01: 156. Is de scan stukgelopen of "
        "zijn de mappen verplaatst, dan meldt deze guard nooit meer iets."
    )


@pytest.mark.architecture
def test_the_exclusion_covers_only_this_file() -> None:
    """De uitzonderingslijst mag alleen dit bestand bevatten, en dat bestand moet bestaan.

    Rood te maken op twee manieren, beide uitgevoerd: een tweede pad aan `EXCLUDED_FROM_SCAN`
    toevoegen, en het enige pad wijzigen naar iets dat niet bestaat. Zonder deze test is de
    uitzondering een gratis uitweg: wie een zwevende verwijzing niet wil oplossen, zet zijn
    bestand erbij en de guard zwijgt.
    """
    eigen = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()

    assert EXCLUDED_FROM_SCAN == (eigen,), (
        f"`EXCLUDED_FROM_SCAN` is {EXCLUDED_FROM_SCAN} en hoort precies ({eigen!r},) te zijn. "
        "De enige legitieme uitzondering is dit bestand zelf, omdat zijn OP-nummers INVOER voor "
        "de regel zijn. Wil je een echte verwijzing uitzonderen: schrijf de registerrij."
    )
    assert (REPO_ROOT / eigen).is_file()


@pytest.mark.architecture
def test_the_register_has_rows_at_all() -> None:
    """Vangnet aan de andere kant: een leeg gelezen register maakt elke verwijzing zwevend."""
    rijen = _register_rows()
    assert len(rijen) >= 150, (
        f"Slechts {len(rijen)} registerrijen gelezen uit de twee registerbestanden. Gemeten "
        "2026-09-01: 174. Is de tabelvorm gewijzigd, dan meldt deze guard straks ELKE verwijzing "
        "als zwevend en is hij niet meer te vertrouwen."
    )


@pytest.mark.architecture
def test_every_op_reference_in_code_has_a_register_row() -> None:
    """DE guard: elk OP-nummer dat code noemt, bestaat als rij in het register.

    Rood te maken door in een willekeurig bestand onder `src/` een comment met `ADR-036 OP-999`
    te zetten, of door een rij uit de registertabel te halen waarnaar code verwijst.
    """
    rijen = _register_rows()
    zwevend = {
        nummer: regels for nummer, regels in _references_in_code().items() if nummer not in rijen
    }

    if zwevend:
        details = []
        for nummer in sorted(zwevend, key=lambda s: int(s[3:])):
            plekken = zwevend[nummer]
            eerste = plekken[0].split(":")[0:2]
            details.append(f"  {nummer}: {len(plekken)}x, eerste op {':'.join(eerste)}")
        raise AssertionError(
            "Deze OP-nummers worden in code genoemd maar bestaan niet als rij in "
            "een van de twee ADR-036-registerbestanden:\n" + "\n".join(details) + "\n\n"
            "Een verwijzing naar een niet-bestaande rij belooft de hele registeradministratie "
            "(status, verificatiedatum, machinaal bewijs) en levert niets. Schrijf de rij, of "
            "haal de verwijzing weg. Dit is twee keer eerder gebeurd: OP-75/76/77 zaten maanden "
            "in een gat in de tabel, en OP-178 stond in zes OpenAPI-beschrijvingen voordat de "
            "rij bestond."
        )
