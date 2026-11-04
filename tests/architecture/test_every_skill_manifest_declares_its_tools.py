"""Elk skill-manifest noemt zijn toegestane tools expliciet (SP-COUNCIL-GATE-001).

Gevonden door de Gate 2-security-reviewer, ronde 2. `specialist_base._parse_tool_calls` filtert
modelgekozen toolnamen alleen `if self.allowed_tools`, en `SkillManifest` maakt van een
ontbrekend veld een lege lijst. Voor een skill zonder `allowed_tools` slaat het filter dus over
en is `tool_name` een WILLEKEURIGE string uit modeluitvoer.

Dat raakt sinds deze sprint meer dan de uitvoering zelf: die naam komt in `message` en
`reasoning` van het Council-voorstel, en die twee velden gaan ONGEREDIGEERD de ADR-019-hashketen
in (`audit_writer.py` haalt alleen `action_params` door `redact_for_publication()`). Een lege
`allowed_tools` betekent dan: modeltekst, permanent, in een record dat per ontwerp niet
corrigeerbaar of wisbaar is -- in strijd met AVG art. 16/17 en met wat
`background_gate.request_council_decision_for_agent` in zijn eigen docstring belooft
("uitsluitend SYSTEEMTEKST meegeven").

**Gemeten 2026-08-16: het gat is nul.** Alle 135 manifesten vullen `allowed_tools`. Deze guard
houdt dat zo; er is geen uitzonderingslijst en die hoort er ook niet te komen. Daarom een
gewone groene guard en geen uitzonderingspatroon: er is niets uit te stellen.

**Mutatietest (2026-08-16), beide richtingen:**
- `allowed_tools` uit `manifests/skillsgaptraining.yml` gehaald -> ROOD, met die bestandsnaam
  in de melding. Op een LEGE lijst (`allowed_tools: []`) eveneens ROOD.
- Ongewijzigd -> GROEN, en `test_the_guard_reads_real_manifests` bewijst dat er daadwerkelijk
  manifesten zijn gelezen; nul manifesten zou de eerste test trivially groen maken.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFESTS = _REPO_ROOT / "src" / "core" / "als" / "agents" / "skills" / "manifests"


def _manifesten() -> dict[str, dict[str, object]]:
    gevonden: dict[str, dict[str, object]] = {}
    for pad in sorted(_MANIFESTS.glob("*.yml")):
        data = yaml.safe_load(pad.read_text(encoding="utf-8-sig")) or {}
        if isinstance(data, dict):
            gevonden[pad.name] = data
    return gevonden


def test_every_manifest_declares_a_non_empty_allowed_tools() -> None:
    """Een lege toollijst zet het naamfilter uit en laat modeltekst de auditketen in."""
    zonder = sorted(
        naam for naam, data in _manifesten().items() if not (data.get("allowed_tools") or [])
    )

    assert not zonder, (
        f"Deze manifesten hebben geen (of een lege) `allowed_tools`: {zonder}.\n\n"
        "`_parse_tool_calls` slaat het naamfilter dan over, en een willekeurige modelstring "
        "belandt via `message` en `reasoning` ongeredigeerd in de onuitwisbare ADR-019-keten. "
        "Vul de lijst, of geef de skill geen tools door hem uit het uitvoerpad te halen."
    )


def test_the_guard_reads_real_manifests() -> None:
    """De tweede richting: nul manifesten maakt de test hierboven trivially groen."""
    manifesten = _manifesten()

    assert len(manifesten) >= 100, (
        f"Slechts {len(manifesten)} manifesten gevonden in {_MANIFESTS}. Op 2026-08-16 waren "
        "het er 135. Is de map verplaatst, dan bewaakt de test hierboven niets."
    )
