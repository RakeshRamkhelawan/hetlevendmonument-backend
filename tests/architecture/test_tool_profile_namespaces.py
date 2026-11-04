"""Architecture test: elk profiel in tool_permissions.yml benoemt zijn naamruimte.

Achtergrond (ADR-036 D10 stap 3 / BE-AGT-039, 2026-08-01):
`config/tool_permissions.yml` bevat twee soorten namen die er identiek uitzien:

  - **council_action** -- Council `action_type`-strings. Worden alleen GECONTROLEERD
    (`_ToolBrokerAdapter.is_allowed`, `copilot/council/factory.py`) en uitgevoerd door de
    copilot-actiehandlers, niet door de ToolBroker. Ze hoeven dus niet te resolveren naar
    een broker-tool.
  - **broker_tool** -- echte toolnamen die via `ToolBrokerService.execute_tool` lopen. Die
    MOETEN resolveren, anders krijgt de agent "Unknown tool category".

Zonder dit onderscheid leest een reviewer 13 "ontbrekende tools" in het copilot-profiel die
geen gat zijn, en krijgt tegelijk geen enkel signaal wanneer een skill-tool werkelijk niet
bestaat. Dat is precies wat er gebeurde: de eerste lezing van de gap-analyse concludeerde
dat 13 copilot-tools stuk waren in productie, wat pas bij het lezen van de adapter onjuist
bleek.

Deze guard dwingt drie dingen af:
  1. elk profiel benoemt zijn naamruimte expliciet;
  2. in de broker-naamruimte resolveert elke tool -- met, indien nodig, een gedateerde
     uitzondering. Die lijst is sinds 2026-09-21 LEEG: de drie piloot-tools bestaan en de
     drie die nooit gebouwd zijn, zijn uit het manifest en het profiel gehaald;
  3. die uitzondering rot niet dicht: zodra een tool wel bestaat, of niemand hem nog
     declareert, faalt een van de twee staleness-tests.
"""

from pathlib import Path

import yaml

CONFIG = Path("config/tool_permissions.yml")

VALID_NAMESPACES = {"council_action", "broker_tool"}

# Exact de check uit ToolBrokerService.execute_tool stap 0a (service.py:166-175).
KNOWN_PREFIXES = ("local__", "test__", "serena__", "sequentialthinking__")
BUSINESS_TOOLS = {"create_task", "list_tasks", "update_task", "delete_task"}


# HR-leestools (BE-AGT-044, 2026-08-02). Uit de bron gehaald en niet overgeschreven, zodat
# deze guard niet stilzwijgend uiteenloopt met wat de broker werkelijk accepteert.
def _hr_tools() -> set[str]:
    from src.core.tool_broker.hr_registry import HRToolRegistry
    from src.core.tool_broker.payables_registry import PayablesToolRegistry
    from src.core.tool_broker.payment_run_registry import BetaalrunToolRegistry
    from src.core.tool_broker.receivables_registry import ReceivablesToolRegistry

    # De debiteurentools (2026-10-05) dispatchen in dezelfde broker; zelfde vraag, andere registry.
    return (
        HRToolRegistry.known_tool_names()
        | ReceivablesToolRegistry.known_tool_names()
        | PayablesToolRegistry.known_tool_names()
        | BetaalrunToolRegistry.known_tool_names()
    )


#: LEEG sinds 2026-09-21, en dat is geen opruiming maar het resultaat: er staat geen tool meer
#: in een broker_tool-profiel die niet bestaat. Beide staleness-tests hieronder hebben dat zelf
#: afgedwongen -- ze werden rood op het moment dat de laatste vier verdwenen, elk om zijn eigen
#: reden:
#:
#:   query_hr_database  2026-08-02  gebouwd (BE-AGT-044)
#:   analyze_skill_gap  2026-08-15  gebouwd (OP-26)
#:   schedule_training  2026-09-21  gebouwd -- de eerste SCHRIJFtool van de HR-registry
#:   search_documents   2026-09-21  uit het manifest EN het profiel gehaald: er is geen
#:                                  documentmodel, dus geen tool en geen data
#:   send_notification  2026-09-21  idem -- er is notificatie-infrastructuur, maar geen
#:                                  broker-tool; deze skill adviseert en meldt niet
#:   generate_text      2026-09-21  bestond al onder zijn echte naam `local__llm_generate`
#:
#: Een naam hier weer toevoegen betekent: een agent krijgt permissie voor iets dat niet
#: bestaat. Dat mag, met datum en reden, maar het is geen vrijblijvende parkeerplaats -- de
#: tweede test hieronder gooit hem eruit zodra niemand hem meer declareert.
KNOWN_UNRESOLVED_BROKER_TOOLS: dict[str, str] = {}


def _profiles() -> list[dict[str, object]]:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    return list(data.get("agent_profiles") or [])


def _tools_of(profile: dict[str, object]) -> list[str]:
    """allowed_tools als lijst van strings, ongeacht of het veld ontbreekt of null is."""
    raw = profile.get("allowed_tools")
    if not isinstance(raw, list):
        return []
    return [str(t) for t in raw]


def _is_executable(tool: str) -> bool:
    return tool.startswith(KNOWN_PREFIXES) or tool in BUSINESS_TOOLS or tool in _hr_tools()


def test_every_profile_declares_its_namespace() -> None:
    """Een profiel zonder naamruimte is niet te beoordelen."""
    missing = [
        str(p.get("agent_id")) for p in _profiles() if p.get("namespace") not in VALID_NAMESPACES
    ]

    assert not missing, (
        "Deze profielen in config/tool_permissions.yml missen een geldige `namespace` "
        f"({sorted(VALID_NAMESPACES)}):\n"
        + "\n".join(f"  - {m}" for m in missing)
        + "\n\nZonder dat veld is niet af te lezen of de namen Council-action_types zijn "
        "(alleen gecontroleerd) of broker-toolnamen (ook uitgevoerd). Zie ADR-036 D10 "
        "stap 3 / BE-AGT-039."
    )


def test_broker_namespace_tools_resolve_or_are_known_gaps() -> None:
    """In de broker-naamruimte moet elke tool uitvoerbaar zijn."""
    unresolved: list[str] = []

    for profile in _profiles():
        if profile.get("namespace") != "broker_tool":
            continue
        agent_id = str(profile.get("agent_id"))
        for tool in _tools_of(profile):
            if _is_executable(tool) or tool in KNOWN_UNRESOLVED_BROKER_TOOLS:
                continue
            unresolved.append(f"{agent_id}: {tool}")

    assert not unresolved, (
        "Deze tools staan in een broker_tool-profiel maar resolveren niet in "
        "ToolBrokerService.execute_tool. De agent krijgt dan 'Unknown tool category' "
        "terug -- de permissie is toegekend voor iets dat niet bestaat:\n"
        + "\n".join(f"  - {u}" for u in unresolved)
        + "\n\nImplementeer de tool, of voeg hem met datum en reden toe aan "
        "KNOWN_UNRESOLVED_BROKER_TOOLS."
    )


def test_known_unresolved_tools_are_not_stale() -> None:
    """Een tool die inmiddels wel bestaat moet uit de uitzonderingslijst."""
    now_resolvable = [
        f"{tool} ({reason})"
        for tool, reason in KNOWN_UNRESOLVED_BROKER_TOOLS.items()
        if _is_executable(tool)
    ]

    assert not now_resolvable, (
        "KNOWN_UNRESOLVED_BROKER_TOOLS is verouderd -- deze tools bestaan nu wel en horen "
        "uit de lijst (Fase 2 is dan deels af):\n" + "\n".join(f"  - {n}" for n in now_resolvable)
    )


def test_known_unresolved_tools_are_actually_declared() -> None:
    """Een uitzondering voor een tool die niemand meer declareert is dode ballast."""
    declared: set[str] = set()
    for profile in _profiles():
        if profile.get("namespace") == "broker_tool":
            declared.update(_tools_of(profile))

    orphans = sorted(set(KNOWN_UNRESOLVED_BROKER_TOOLS) - declared)

    assert not orphans, (
        "Deze uitzonderingen gelden tools die geen enkel broker_tool-profiel meer "
        f"declareert; haal ze weg: {orphans}"
    )
