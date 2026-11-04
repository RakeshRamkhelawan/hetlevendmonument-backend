"""Architecture test: geen non-ASCII in de ADR-036 kernzone (BE-AGT-043).

CLAUDE.md par. 3 verbiedt emoji en non-ASCII in code, comments en logs. Die regel had tot
2026-08-02 geen enkele handhaving: bij de onafhankelijke hercontrole van de ADR-036-fasen
bleken er repo-breed 301 bestanden met 1049 regels non-ASCII te staan, en niets dat een
nieuwe erbij tegenhield.

**Waarom deze guard alleen de kernzone dekt.** Een uitzonderingslijst met 301 regels is
precies de "kale set" die `.claude/rules/quality-gates.md` verbiedt -- een lijst die niemand
meer leest is geen borging. De zone hieronder is de code die ADR-036 daadwerkelijk raakt en
telde 8 bestanden met 23 regels; die zijn schoongemaakt in dezelfde commit als deze guard.
Daardoor kan de uitzonderingslijst LEEG blijven, en dat is een sterkere borging dan welke
gedateerde lijst ook. Het repo-brede restant staat als OP-22 in ADR-036 par. 10.

**Waarom dit meer is dan cosmetiek.** Tussen de 23 gevonden regels zaten twee echte
defecten: `api/v1/agentic/learning.py` had een dubbel-gecodeerde em-dash (mojibake) en
`api/v1/agentic/monitoring.py` begon met een UTF-8 BOM. Beide zijn onzichtbaar in een
diff-weergave en beide veroorzaken problemen bij tooling die op ASCII rekent.

`Path.rglob` en niet ripgrep: die laatste heeft de blinde vlek uit OP-17.
"""

from pathlib import Path

# Vanaf __file__ en niet CWD-relatief: draait pytest vanuit een andere map, dan zou geen
# enkele zone bestaan, vond de scan niets en slaagde deze guard vacuum.
REPO_ROOT = Path(__file__).resolve().parents[2]

# De code die ADR-036 raakt. Bewust expliciet en niet "heel src/" -- zie de docstring.
CORE_ZONES = (
    REPO_ROOT / "src/core/als/agents",
    REPO_ROOT / "src/core/tool_broker",
    REPO_ROOT / "src/core/copilot/council",
    REPO_ROOT / "src/core/api/v1/agentic",
)

# Gedateerde uitzonderingen: pad -> reden. LEEG bij oplevering van BE-AGT-043 en dat hoort
# zo te blijven. Een regel hier toevoegen vraagt een reden en een datum, geen kaal pad.
KNOWN_NON_ASCII: dict[str, str] = {}


def _violations() -> tuple[list[tuple[str, int, str]], list[str]]:
    """(pad, regelnummer, de regel) voor elke regel met een teken buiten ASCII, plus
    paden die niet gelezen konden worden.

    Een bestand dat NIET als UTF-8 decodeert (bijv. per ongeluk Windows-1252) is
    precies het ergste geval van de klasse die deze guard moet vangen -- en werd
    voorheen stil overgeslagen, zonder telling.
    """
    found: list[tuple[str, int, str]] = []
    fouten: list[str] = []
    for zone in CORE_ZONES:
        if not zone.exists():
            continue
        for path in sorted(zone.rglob("*.py")):
            key = path.relative_to(REPO_ROOT).as_posix()
            if key in KNOWN_NON_ASCII:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                fouten.append(f"{key}: {exc}")
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if any(ord(char) > 127 for char in line):
                    offending = sorted({f"U+{ord(c):04X}" for c in line if ord(c) > 127})
                    found.append((key, number, ", ".join(offending)))
    return found, fouten


def test_core_zones_exist() -> None:
    """Vangnet: een hernoemde map mag deze guard niet stilzwijgend vacuum maken.

    Zonder deze test zou het verplaatsen van bijvoorbeeld `src/core/tool_broker` de scan
    hierboven voor iedereen laten slagen -- er valt dan niets meer te vinden omdat er
    nergens meer gekeken wordt.
    """
    missing = [str(zone) for zone in CORE_ZONES if not zone.exists()]

    assert not missing, (
        f"Deze zonepaden bestaan niet meer: {missing}. Hernoemd of verplaatst? Werk dan "
        "CORE_ZONES bij -- anders controleert deze guard niets meer."
    )


def test_no_source_file_is_silently_unreadable() -> None:
    """Vangnet: een bestand dat niet als UTF-8 decodeert mag niet stilzwijgend overgeslagen worden.

    Zo'n bestand is precies het ergste geval van de klasse die deze guard moet vangen --
    het bevat per definitie tekens buiten ASCII, en werd voorheen zonder telling genegeerd.
    """
    _, fouten = _violations()
    assert not fouten, (
        "Deze bestanden in de kernzone konden niet als UTF-8 gelezen worden en zijn NIET "
        "gecontroleerd op non-ASCII:\n" + "\n".join(f"  - {f}" for f in fouten)
    )


def test_no_non_ascii_in_core_zone() -> None:
    """Geen enkel teken buiten ASCII in de kernzone (CLAUDE.md par. 3)."""
    violations, _fouten = _violations()

    rendered = "\n".join(f"  - {path}:{number}  ({chars})" for path, number, chars in violations)

    assert not violations, (
        "Deze regels bevatten tekens buiten ASCII, wat CLAUDE.md par. 3 verbiedt in code, "
        "comments en logs:\n"
        f"{rendered}\n\n"
        "Vervang em-dashes door '--', box-tekens door '|--' en '`--', en verwijder emoji. "
        "Let op twee stille gevallen: een dubbel-gecodeerde em-dash (mojibake) leest als "
        "'a-hat-euro-quote', en een UTF-8 BOM staat onzichtbaar voor het eerste teken van "
        "regel 1."
    )


def test_known_non_ascii_list_is_not_stale() -> None:
    """Een uitzondering voor een bestand dat schoon is, is dode ballast.

    De lijst is leeg bij oplevering. Deze test zorgt dat hij niet stilletjes gevuld blijft
    nadat iemand het onderliggende bestand heeft opgeschoond.
    """
    stale = []
    for key, reason in KNOWN_NON_ASCII.items():
        path = REPO_ROOT / key
        if not path.exists():
            stale.append(f"{key} (bestaat niet meer) -- {reason}")
            continue
        text = path.read_text(encoding="utf-8")
        if all(ord(char) <= 127 for char in text):
            stale.append(f"{key} (is inmiddels schoon) -- {reason}")

    assert not stale, "Deze uitzonderingen kunnen weg uit KNOWN_NON_ASCII:\n" + "\n".join(
        f"  - {entry}" for entry in stale
    )
