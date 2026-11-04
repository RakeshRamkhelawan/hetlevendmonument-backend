"""Het HITL-ticket is een ZEVENDE bewarende sink, en dat is geregistreerd (ADR-036 OP-47).

**De bevinding.** `copilot/service.py` geeft bij een `HITL_REQUIRED`-verdict
`dict(proposal.action_params)` ONBEWERKT aan `HITLTicketRepository.create_hitl_request`, die het
samenvoegt in `payload` en wegschrijft naar `hitl_tickets.payload` (JSONB, NOT NULL). Dat is
dezelfde dict die `persist()` sinds OP-33 pseudonimiseert -- een functieaanroep later staat hij dus
rauw op schijf.

Live gewired: `copilot/dependencies.py:115` construeert de repository en geeft hem op regel 123 mee.

**Wat dit betekende voor twee beweringen die ik zelf heb geschreven.** OP-33 noemde de council-sink
"een ZESDE bewarende sink ... en het is de enige die vandaag live is", en de art.-17(3)(b)-alinea
sprak van "drie bewarende plekken". Het zijn er zeven respectievelijk vier, en er zijn er minstens
twee live. Dat is dezelfde categorie fout die in ronde 5 als blokkerend is behandeld: een onjuiste
bewering op een gezaghebbende plek.

**En deze alinea beweerde vervolgens zelf iets onwaars.** Er stond "beide teksten zijn in dezelfde
commit rechtgezet". De blinde review van ronde 7 heeft nagemeten dat alleen de ADR was
bijgewerkt; de claim leefde nog in de moduledocstring van `redaction.py`, in
`test_council_persist_leaks_nothing.py`, in de feature-spec en in het reviewdocument. Dat is op
2026-08-05 alsnog gedaan. Les die hierbij hoort: "ik heb X rechtgezet" is zelf een bewering die
gemeten hoort te worden voordat je hem opschrijft -- met `git grep`, niet uit het hoofd.

De opsomming van de zeven plekken met de stand per plek staat sinds die correctie op EEN plek: de
moduledocstring van `src/core/tool_broker/redaction.py`. Verwijs daarheen in plaats van het aantal
te herhalen; vier kopieen van een getal is hoe dit drie keer misging.

**Waarom niet simpelweg redigeren.** Het HITL-ticket is de bewuste uitzondering: wie een actie
goedkeurt moet zien wat hij goedkeurt (AI Act art. 14). Dat argument staat al in
`KNOWN_RAW_PAYLOAD_SITES` voor `hitl_store.py` en het geldt hier onverkort. Wat het WEL vraagt is
een retentie- of wisroute, en die is er niet: `cleanup_expired` zet alleen `status="expired"` en een
`git grep` op `hitl_ticket` in `retention_cleanup.py`, `jobs/` en `learning/` is leeg. Goede nieuws
voor de oplosbaarheid: `hitl_tickets` heeft GEEN hash-keten, dus blanken bij resolutie of expiry
breekt niets -- anders dan bij `council_decisions.action_params`, dat in
`compute_canonical_json` zit.

**Waarom een eigen guard.** De sink-guard in `test_tool_payloads_are_pseudonymised.py` kan dit niet
zien zonder `create` aan `SINKS` toe te voegen, en dat vlagt `business_registry.py:133`
(`service.create(task_in)` -- de tool die zijn werk doet) als valse positief. Een guard met valse
positieven wordt uitgezet in plaats van vervuld, dus staat het schrijfpad hier apart.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Aanroepplekken die `action_params` ONBEWERKT aan het HITL-ticket geven. Pad -> reden, gedateerd.
#: Leeg maken zodra OP-47 is opgelost (een retentie- of wisroute, of blanken bij resolutie).
KNOWN_RAW_HITL_WRITES: dict[str, str] = {
    "src/core/copilot/service.py": (
        "2026-08-04, OP-47, Fase B/P1 -- `_route_verdict` geeft dict(proposal.action_params) rauw "
        "aan create_hitl_request bij een HITL_REQUIRED-verdict. Het BEWAREN is de bewuste "
        "art.-14-uitzondering (de goedkeurder moet zien wat hij goedkeurt); wat ontbreekt is een "
        "retentie- of wisroute. cleanup_expired markeert alleen status='expired' en verwijdert "
        "niets. Oplosbaar zonder de keten te breken: hitl_tickets heeft geen hash-keten."
    ),
    "src/core/copilot/council/background_gate.py": (
        "2026-08-25, OP-167, open-punten-opruiming dag 1 -- `request_council_decision_for_agent` "
        "maakt nu zelf een ticket aan bij een RAUW HITL_REQUIRED-verdict en geeft daarbij "
        "`ticket_action_params` (of, zonder die parameter, `action_params` zelf) onbewerkt aan "
        "`create_hitl_request`. Zelfde OP-47-redenering als het bestaande write-pad hierboven: "
        "BEWAREN is de bewuste art.-14-uitzondering, wat ontbreekt is dezelfde retentie- of "
        "wisroute -- geen nieuw, apart gat, hetzelfde gat op een tweede schrijfplek."
    ),
    "src/core/als/agents/specialist_base.py": (
        "2026-08-25, OP-167, open-punten-opruiming dag 1 (Gate 2-bevinding) -- "
        "`_council_rejection()`'s D4-002-floor-tak (de piloot-skill die een APPROVED-verdict "
        "lokaal optilt naar HITL_REQUIRED) roept `create_hitl_request(..., action_params=params, "
        "...)` rechtstreeks aan, ONGEWIJZIGD sinds voor deze sprint -- geen nieuwe wijziging, maar "
        "wel voor het eerst gevonden doordat deze code vandaag toch al werd aangeraakt. Zelfde "
        "OP-47-redenering: BEWAREN is de bewuste art.-14-uitzondering, wat ontbreekt is dezelfde "
        "retentie- of wisroute. `_SCAN_ROOTS` miste `src/core/als` sinds het ontstaan van deze "
        "guard -- de moduledocstring noemt `copilot` expliciet als eerdere blinde vlek, `als` was "
        "een tweede, nog niet ontdekte blinde vlek van dezelfde soort."
    ),
    "src/core/copilot/council/governance_gate.py": (
        "2026-08-25, OP-167, open-punten-opruiming/HITL-ticket-volledigheid sprint dag 2 -- "
        "`require_council_approval` maakt nu een ticket aan bij een HITL_REQUIRED-verdict "
        "(met `db` meegegeven) en geeft `ticket_action_params` (of, zonder die parameter, "
        "`action_params` zelf) onbewerkt door. Zelfde OP-47-redenering als de bestaande "
        "regels hierboven -- BEWAREN is de bewuste art.-14-uitzondering, wat ontbreekt is "
        "dezelfde retentie- of wisroute."
    ),
    "src/core/api/v1/focus_builder/execution_router.py": (
        "2026-08-25, OP-167, HITL-ticket-volledigheid sprint dag 2 -- `execute_flow` maakt nu "
        "een ticket aan bij een HITL_REQUIRED-verdict en geeft "
        "`dict(proposal.action_params)` onbewerkt door, zelfde patroon als "
        "`copilot/service.py` hierboven. Zelfde OP-47-redenering."
    ),
}

#: De methode die het ticket aanmaakt uit een council-verdict.
_ENTRY_POINT = "create_hitl_request"

#: De sleutel waaronder de rauwe payload wordt doorgegeven.
_RAW_KEYWORD = "action_params"

#: Mappen die op deze aanroep worden gescand. Bewust breder dan `tool_broker`: de AANROEPER staat in
#: `copilot`/`als`, en juist dat was de blinde vlek -- de sink-guard scant alleen
#: tool_broker-mappen.
_SCAN_ROOTS = ("src/core/copilot", "src/core/tool_broker", "src/core/api", "src/core/als")


def _callers() -> tuple[dict[str, list[int]], list[str]]:
    """(bestand -> regelnummers waar create_hitl_request(action_params=...) wordt aangeroepen,
    paden die niet gelezen/geparsed konden worden)."""
    found: dict[str, list[int]] = {}
    fouten: list[str] = []
    for root in _SCAN_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            except (OSError, SyntaxError, UnicodeDecodeError) as exc:
                fouten.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {exc}")
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name != _ENTRY_POINT:
                    continue
                if any(keyword.arg == _RAW_KEYWORD for keyword in node.keywords):
                    relative = path.relative_to(REPO_ROOT).as_posix()
                    found.setdefault(relative, []).append(node.lineno)
    return found, fouten


def test_the_scan_finds_the_hitl_entry_point() -> None:
    """Vangnet: zonder gevonden aanroeper bewaakt deze guard niets.

    Zonder deze test maakt een hernoemde methode of een verplaatste map de scan stil leeg, en dan
    meldt de guard niets terwijl de rauwe payload nog steeds wordt weggeschreven.
    """
    callers, _fouten = _callers()

    assert callers, (
        f"Geen enkele aanroep van {_ENTRY_POINT}(...{_RAW_KEYWORD}=...) gevonden in {_SCAN_ROOTS}. "
        "Hernoemd of verplaatst? Werk deze guard bij -- anders bewaakt hij niets."
    )


def test_no_source_file_is_silently_unreadable() -> None:
    """Vangnet: een onleesbaar/onparseerbaar bestand mag deze guard niet blind maken.

    De "niet-leeg"-controle hierboven beschermt alleen tegen een totaal lege scan -- die
    blijft niet-leeg zolang de bekende gevallen in KNOWN_RAW_HITL_WRITES de scan vullen.
    Een NIEUW bestand met een syntaxfout en een onbewerkte HITL-schrijfactie erin zou
    daardoor stil buiten de scan vallen.
    """
    _, fouten = _callers()
    assert not fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden en zijn NIET gecontroleerd op "
        "een onbewerkte HITL-ticket-schrijfactie:\n" + "\n".join(f"  - {f}" for f in fouten)
    )


def test_no_new_raw_hitl_write() -> None:
    """Een NIEUWE aanroeper die de rauwe payload doorgeeft, is geblokkeerd."""
    callers, _fouten = _callers()
    offenders = sorted(path for path in callers if path not in KNOWN_RAW_HITL_WRITES)

    assert not offenders, (
        f"Deze plekken geven action_params onbewerkt aan het HITL-ticket: {offenders}. "
        "Dat landt in "
        "hitl_tickets.payload (JSONB, NOT NULL) waarvoor GEEN retentie- of wisroute bestaat. Het "
        "BEWAREN kan verdedigbaar zijn onder AI Act art. 14 -- wie goedkeurt moet zien wat hij "
        "goedkeurt -- maar dan hoort het met datum en reden in KNOWN_RAW_HITL_WRITES, zodat de "
        "bewaartermijn een beslissing is en geen bijproduct."
    )


def test_known_raw_hitl_writes_is_not_stale() -> None:
    """Een aanroeper die de rauwe payload niet meer doorgeeft, hoort uit de lijst."""
    callers, _fouten = _callers()
    stale = sorted(path for path in KNOWN_RAW_HITL_WRITES if path not in callers)

    assert not stale, (
        f"Deze vermeldingen geven action_params niet meer rauw door: {stale}. Haal ze uit "
        "KNOWN_RAW_HITL_WRITES, anders dekt de lijst iets anders dan hij beweert."
    )
