"""Een HR-agent verklaart zijn AI Act-classificatie eerlijk (ADR-036 OP-144).

Gemeten 2026-08-16. `manifests/skillsgaptraining.yml` zei `annex_iii_classification: none`,
terwijl die agent personeelsgegevens leest en per functie een oordeel over vaardigheidskloven
produceert. EU AI Act bijlage III punt 4 noemt systemen die worden gebruikt bij het beheer van
werknemers en bij besluiten die arbeidsverhoudingen raken, expliciet hoogrisico.

**Opgelost 2026-08-18 (ADR-036 D4-001, fix-sprint dag 3) voor de piloot.**
`skillsgaptraining.yml` verklaart nu `annex_iii_classification: annex_iii` /
`human_in_the_loop: hitl`, en `_council_rejection()` (`specialist_base.py`, D4-002) leest dat
manifestveld sindsdien ook echt: een unaniem APPROVED-Councilverdict laat de piloot niet meer
automatisch door. De verklaring was tot dan niet cosmetisch maar ZONDER gevolg -- geen enkele
laag in de Council keek naar dit veld. Sinds D4-002 heeft de eigen verklaring van het manifest
dus voor het eerst een echt, afdwingend gevolg voor DEZE agent.

De verklaring blijft daarnaast los van een TWEEDE, onafhankelijke classificatie: `_ComplianceAdapter`
(`copilot/council/factory.py`) leidt zijn eigen risicoklasse af uit `department` en
`capabilities`; `hr_culture` staat niet in `HIGH_RISK_DEPARTMENTS`
(`governance/ai_act_classifier.py`) en `query_hr_database` matcht geen enkel woord uit
`HIGH_RISK_KEYWORDS`. Die uitkomst (`LIMITED` -> `LOW_RISK`) verandert NIET door de
D4-001/D4-002-fix (gemeten, zie de comment boven `action_params` in
`specialist_base.py::_council_rejection`) -- de ComplianceOfficer beoordeelt de HR-tools dus nog
steeds als laag risico op basis van DIE classificatie. De D4-002-floor werkt volledig los
daarvan: hij dwingt HITL_REQUIRED af op basis van het manifestveld, ongeacht wat een Officer
concludeert.

**Tien van de elf resterende HR-manifesten verklaren nog `none` voor dezelfde datatoegang.**
De overwegingen hieronder blijven voor HEN van toepassing. (`taskmanager.yml` opgelost
2026-08-25, open-punten-opruiming BE-AGT-063 -- zie hieronder.)

**Wat dit NIET is (voor de resterende elf).** Het is geen bewering dat ze vandaag onrechtmatig
draaien: de verplichtingen voor bijlage III-systemen zijn met de Digital Omnibus verschoven naar
2 december 2027. Het is wel een bewering dat het MANIFEST iets anders zegt dan wat het systeem
doet, en dat een verkeerde verklaring de hele governanceketen eronder verkeerd instelt.

**Waarom een groene guard met uitzondering.** De classificatie omzetten naar `employment`
verandert de risicoklasse van elke actie van deze agent, en daarmee welke acties een mens
vooraf moet zien. Dat is een productbeslissing met een eigen meting, en `HIGH_RISK_DEPARTMENTS`
moet er dan ook op aangepast worden -- anders verandert er alsnog niets en ziet het er alleen
uit alsof er iets is opgelost.

**Het criterium is DATATOEGANG, niet de afdeling.** Een eerdere versie van deze guard keek
naar `department: hr_culture` en betrapte daarmee ook agents die geen personeelsdata lezen.
Gemeten met het huidige criterium: vijftien manifesten gebruiken `query_hr_database` of
`analyze_skill_gap`. Vijf daarvan (`skillsgaptraining`, `employeesentiment`,
`internalmobility`, `talentacquisition`, `taskmanager`) verklaren `annex_iii`; de andere tien
verklaren `none` voor exact dezelfde datatoegang. Die tegenstelling BINNEN de codebase is het
bewijs dat dit een omissie is en geen weloverwogen keuze.

**`taskmanager.yml` opgelost 2026-08-25 (open-punten-opruiming, BE-AGT-063).** Het manifest
verklaart nu `annex_iii`/`hitl`. Companion-check uitgevoerd conform de OP-165-nazorg-eis
hierboven: `department: taskmanager.yml`'s `hr_culture` staat niet in `HIGH_RISK_DEPARTMENTS`
(`governance/ai_act_classifier.py`) -- exact dezelfde conclusie als eerder gemeten voor
`skillsgaptraining` (ook `department: hr_culture`). Geen wijziging aan
`ai_act_classifier.py` nodig; de `_ComplianceAdapter`-classificatie blijft `LIMITED` ->
`LOW_RISK`, ongewijzigd door deze reclassificatie -- exact zoals bij de piloot.

**Mutatietest, beide richtingen:**
- Een tweede HR-manifest met `annex_iii_classification: none` toegevoegd -> ROOD op
  `test_no_new_hr_agent_declares_none`, met dat bestand in de melding.
- `skillpathfinder.yml` op `employment` gezet -> ROOD op `test_the_known_gap_is_not_stale`
  (2026-08-16, aangetoond met `skillsgaptraining.yml` -- dezelfde mutatie die op 2026-08-18
  voor die agent daadwerkelijk is doorgevoerd, zie hierboven).
- Ongewijzigd -> GROEN, en `test_the_guard_reads_real_manifests` bewijst dat er daadwerkelijk
  manifesten met een HR-datatool zijn gelezen; een lege verzameling zou de eerste test
  trivially groen maken.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MANIFESTS = _REPO_ROOT / "src" / "core" / "als" / "agents" / "skills" / "manifests"

# Tools die personeelsgegevens ontsluiten. Het criterium is DATATOEGANG, niet de afdeling:
# een pauzeherinnering in `hr_culture` valt niet onder bijlage III, een agent die
# personeelsdossiers leest wel -- ongeacht onder welke afdeling hij hangt.
_HR_DATA_TOOLS = {"query_hr_database", "analyze_skill_gap"}

# Gedateerd 2026-08-16, reden per regel. Alle tien lezen personeelsgegevens via
# `query_hr_database` en verklaren toch `none`, terwijl vijf zusteragents met exact
# dezelfde tool (`skillsgaptraining`, `employeesentiment`, `internalmobility`,
# `talentacquisition`, `taskmanager`) wel `annex_iii` verklaren. Die tegenstelling binnen een
# codebase is het bewijs dat dit een omissie is en geen weloverwogen keuze -- OP-144.
#
# `skillsgaptraining.yml` stond hier tot 2026-08-18 ook in (de piloot) -- verwijderd toen die
# agent daadwerkelijk `annex_iii`/`hitl` ging verklaren EN dat veld voor het eerst een echt
# gevolg kreeg (ADR-036 D4-001/D4-002, fix-sprint dag 3). `taskmanager.yml` stond hier tot
# 2026-08-25 ook in (open-punten-opruiming, BE-AGT-063) -- verwijderd op dezelfde grond, zijn
# eigen docstring maakte de classificatie al onmiskenbaar.
#
# Elke reden hieronder draagt ook een voorlopige inschatting (open-punten-opruiming,
# 2026-08-25, GEEN manifestwijziging): "waarschijnlijk annex_iii" betekent dat de datatoegang
# even direct is als bij de vijf al-geclassificeerde agents; "waarschijnlijk none, niet
# vastgesteld" betekent dat de tool wel is toegekend maar het gebruik ervan er zwakker naar
# uitziet. Beide blijven ONBESLIST totdat Rakesh per agent kijkt.
# OP-144 volledig gesloten op 2026-08-25: alle 11 HR-agents zijn expliciet
# geclassificeerd conform de beleidsbeslissing van Rakesh. 7 agents verklaren
# nu `annex_iii`/`hitl`, en de 4 ondersteunende agents hebben geen toegang meer
# tot `query_hr_database` (data-minimalisatie). KNOWN_UNDECLARED is nu leeg.
KNOWN_UNDECLARED: dict[str, str] = {}


def _manifesten_met_hr_data() -> dict[str, dict[str, object]]:
    """Manifesten waarvan `allowed_tools` een personeelsdata-tool bevat."""
    gevonden: dict[str, dict[str, object]] = {}
    if not _MANIFESTS.exists():
        return gevonden
    for pad in sorted(_MANIFESTS.glob("*.yml")):
        data = yaml.safe_load(pad.read_text(encoding="utf-8-sig")) or {}
        if not isinstance(data, dict):
            continue
        if set(data.get("allowed_tools") or []) & _HR_DATA_TOOLS:
            gevonden[pad.name] = data
    return gevonden


def _verklaart_niets(data: dict[str, object]) -> bool:
    return str(data.get("annex_iii_classification", "none")).lower() in {"none", ""}


def test_no_new_hr_agent_declares_none() -> None:
    """Een nieuwe HR-agent die `none` verklaart, is geblokkeerd."""
    onverklaard = sorted(
        naam
        for naam, data in _manifesten_met_hr_data().items()
        if _verklaart_niets(data) and naam not in KNOWN_UNDECLARED
    )

    assert not onverklaard, (
        f"Deze HR-manifesten verklaren `annex_iii_classification: none`: {onverklaard}. Ze "
        "verwerken personeelsgegevens, dus de ComplianceOfficer beoordeelt ze daarmee als laag "
        "risico terwijl bijlage III punt 4 van toepassing kan zijn. Verklaar de classificatie, "
        "of leg in de ADR vast waarom `none` hier klopt."
    )


def test_the_known_gap_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst."""
    manifesten = _manifesten_met_hr_data()
    opgelost = sorted(
        naam
        for naam in KNOWN_UNDECLARED
        if naam in manifesten and not _verklaart_niets(manifesten[naam])
    )

    assert not opgelost, (
        f"Deze manifesten verklaren nu wel een classificatie: {opgelost}. Haal ze uit "
        "KNOWN_UNDECLARED, sluit OP-144 in ADR-036 en controleer of HIGH_RISK_DEPARTMENTS "
        "mee is aangepast -- anders verandert de uitkomst van de ComplianceOfficer niet."
    )


def test_the_guard_reads_real_manifests() -> None:
    """De tweede richting: zonder manifesten is de eerste test trivially groen."""
    assert _MANIFESTS.exists(), f"{_MANIFESTS} bestaat niet."
    manifesten = _manifesten_met_hr_data()
    assert manifesten, (
        "Geen enkel manifest met een HR-datatool gevonden. Op 2026-08-16 waren het er "
        "vijftien. Is de map verplaatst of heet `allowed_tools` anders, dan bewaakt de "
        "test hierboven niets."
    )
