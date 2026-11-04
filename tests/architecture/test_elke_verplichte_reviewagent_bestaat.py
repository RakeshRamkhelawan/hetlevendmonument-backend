"""Elke agent die Gate 2 verplicht stelt, bestaat ook echt (ADR-036 OP-262).

WAT HIER MIS WAS
----------------
`.claude/rules/quality-gates.md` schrijft onder "Gate 2" twee agents voor en zegt erbij dat
beiden GO moeten geven. Gemeten 2026-09-18: `.claude/agents/` bevatte code-reviewer,
security-reviewer, performance-reviewer, doc-reviewer en frontend-designer -- geen
quality-reviewer. `git log --all -- .claude/agents/quality-reviewer.md` geeft NUL commits,
dus dat bestand is nooit aangemaakt en ook nooit verwijderd.

De helft van een verplichte poort verwees dus jarenlang naar iets dat niet bestond, terwijl
`docs/AGENTS.md:87` de rol volledig uitschrijft inclusief checklist en outputformaat. Elke
vastgelegde "beiden GO" is daarmee gegeven op een agent die niet bestond. Dat is dezelfde
faalvorm als een holle guard, maar dan op het PROCES: de controle meldde groen en er werd
niets gecontroleerd. Een sessie merkt het alleen als zij toevallig probeert die agent te
spawnen -- en dan nog krijgt zij een onbekend-agenttype-melding die makkelijk wordt
weggeredeneerd als een eigenaardigheid van haar omgeving.

WAAROM DEZE GUARD OP STRUCTUUR TOETST EN NIET OP TEKST
------------------------------------------------------
De verleiding is om alle instructiebestanden af te zoeken op namen die op een agent lijken.
Dat is precies de faalvorm uit `.claude/rules/quality-gates.md` ("ik doorzocht TEKST waar ik
STRUCTUUR moest toetsen"): proza noemt agents in voorbeelden, in verleden tijd en in
opsommingen van wat er OOK nog kan. Deze guard leest daarom exact een plek -- de opsomming
direct onder de kop "## Gate 2" in `quality-gates.md` -- en eist dat elke naam daar een
bestand heeft. Dat is de enige lijst die bindend is; de rest van de documentatie beschrijft.

MUTATIEBEWIJS (2026-09-18, beide richtingen, een regel per bewaakt element)
--------------------------------------------------------------------------
    quality-reviewer.md hernoemd                          -> ROOD (bestand ontbreekt)
    derde agent aan de Gate 2-opsomming, zonder bestand   -> ROOD (nieuwe eis, geen agent)
    agentbestand met een andere `name:` in de frontmatter -> ROOD (naam telt, niet de bestandsnaam)
    ongemuteerd                                           -> GROEN
"""

from __future__ import annotations

import re
from pathlib import Path

_WORTEL = Path(__file__).resolve().parents[2]
_REGELS = _WORTEL / ".claude" / "rules" / "quality-gates.md"
_AGENTMAP = _WORTEL / ".claude" / "agents"


def _verplichte_gate2_agents() -> dict[str, int]:
    """{agentnaam: regelnummer} uit de opsomming direct onder de kop "## Gate 2"."""
    gevonden: dict[str, int] = {}
    in_gate2 = False
    for nummer, regel in enumerate(_REGELS.read_text(encoding="utf-8").splitlines(), start=1):
        if regel.startswith("## "):
            in_gate2 = regel.startswith("## Gate 2")
            continue
        if not in_gate2:
            continue
        # Alleen de opsomming zelf: "- <naam>: <wat hij doet>". Proza eronder telt niet mee.
        treffer = re.match(r"^- ([a-z][a-z0-9-]+):", regel)
        if treffer:
            gevonden[treffer.group(1)] = nummer
    return gevonden


def _bestaande_agents() -> dict[str, Path]:
    """{naam uit de frontmatter: bestand}. De NAAM telt, want daarmee wordt hij gespawned."""
    gevonden: dict[str, Path] = {}
    for pad in sorted(_AGENTMAP.glob("*.md")):
        for regel in pad.read_text(encoding="utf-8").splitlines()[:10]:
            treffer = re.match(r"^name:\s*([A-Za-z0-9_-]+)\s*$", regel)
            if treffer:
                gevonden[treffer.group(1)] = pad
                break
    return gevonden


def test_elke_verplichte_reviewagent_bestaat() -> None:
    """Gate 2 mag geen agent eisen die niet te spawnen is."""
    verplicht = _verplichte_gate2_agents()
    bestaand = _bestaande_agents()
    ontbreekt = {naam: regel for naam, regel in verplicht.items() if naam not in bestaand}

    assert not ontbreekt, (
        "Gate 2 eist agents die niet bestaan in .claude/agents/: %s. Een verplichte "
        "reviewronde op een niet-bestaande agent levert een GO op die niemand heeft gegeven "
        "(ADR-036 OP-262). Schrijf de agentdefinitie, of haal de eis uit quality-gates.md."
        % ontbreekt
    )


def test_de_gate2_opsomming_wordt_uberhaupt_gevonden() -> None:
    """Zonder deze helft is een kapotte parser niet van een gezonde poort te onderscheiden.

    De guard hierboven wordt groen van een LEGE verplichte-lijst. Als iemand de kop
    hernoemt of de opsomming anders opmaakt, bewaakt hij dan niets meer zonder ooit rood te
    worden. Dit is de tegenrichting.
    """
    verplicht = _verplichte_gate2_agents()
    assert len(verplicht) >= 2, (
        "In quality-gates.md staan onder '## Gate 2' minder dan twee agents (%s). Ofwel de "
        "poort is versoepeld, ofwel deze parser leest de opsomming niet meer." % verplicht
    )
    assert "code-reviewer" in verplicht, (
        "code-reviewer staat niet meer in de Gate 2-opsomming -- dat is of een echte "
        "versoepeling of een leesfout van deze guard; beide horen bekeken te worden."
    )


def test_elke_agentdefinitie_heeft_een_naam() -> None:
    """Een agentbestand zonder `name:` is niet te spawnen en telt dus niet mee."""
    zonder_naam = [
        pad.name
        for pad in sorted(_AGENTMAP.glob("*.md"))
        if pad.name not in {p.name for p in _bestaande_agents().values()}
    ]

    assert not zonder_naam, (
        "Deze agentbestanden hebben geen `name:` in hun frontmatter en zijn daardoor niet "
        "te spawnen: %s" % zonder_naam
    )
