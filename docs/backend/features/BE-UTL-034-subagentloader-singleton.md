# BE-UTL-034 -- SubagentLoader Echte Singleton (SP-WE-12)

**ID:** BE-UTL-034
**Sprint:** SP-WE-12
**Datum:** 2026-06-01
**Bron:** CG-005b (L3 wiring audit 2026-06-01)
**ADR:** ADR-023

---

## Samenvatting

`SubagentLoader` had een nep-singleton: `WorkflowEngine` en `ProductionAgentRuntime` sloegen
de instantie op als instance attribute bij `__init__`. Na `reset_loader()` of `initialize_loader()`
hielden deze objecten een verouderde, losgekoppelde instantie vast. Fix: thread-safe
double-checked locking in `get_loader()`, idempotente `initialize_loader(force=False)` guard,
lock-protected `reset_loader()`, lazy `@property` in beide consumers.

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/subagent_loader.py` | Thread-safe `get_loader()` + `initialize_loader(force=)` guard + lock in `reset_loader()`; pre-existing `"Agent" \| None` runtime TypeError gefixed (`Any`) |
| `src/core/agents/workflow_engine.py` | `self.subagent_loader = ...` verwijderd uit `__init__`; lazy `@property` toegevoegd |
| `src/core/workflow/providers.py` | Zelfde patroon; `load_agent()` None-guard toegevoegd |

## Trainingssamenvatting

### Flow 1: SubagentLoader singleton aanroepen

- Actor: Applicatie-component (WorkflowEngine, CopilotService, endpoint handler)
- Voorwaarde: Applicatie opgestart; `_global_loader` kan None of al geinitialiseerd zijn
- Actie: Component roept `get_loader()` of `get_subagent_loader()` aan
- Systeemverwerking: Thread-safe double-checked lock; maakt SubagentLoader aan als `_global_loader is None`; retourneert altijd dezelfde referentie
- Succesrespons: Zelfde `SubagentLoader`-instantie retourneert ongeacht hoe vaak aangeroepen
- Foutrespons: Geen -- `get_loader()` faalt niet; `SubagentLoader.__init__()` is side-effect-vrij buiten logging
- Uitzonderingen: `reset_loader()` (test-utility) zet `_global_loader = None` onder lock; volgende `get_loader()` maakt nieuwe instantie aan

### Flow 2: initialize_loader() tijdens applicatie-opstart

- Actor: `src/main.py` of startup-hook
- Voorwaarde: Applicatie start op; productie-configuratie beschikbaar
- Actie: `initialize_loader(config, force=False)` aangeroepen
- Systeemverwerking: Als `_global_loader is None`: maakt nieuwe instantie met config. Als singleton al bestaat en `force=False`: retourneert bestaande instantie (idempotent). Double-checked lock voorkomt race bij gelijktijdige eerste aanroep
- Succesrespons: Geconfigureerde singleton beschikbaar voor alle volgende `get_loader()`-aanroepen
- Foutrespons: n.v.t. -- slechte config geeft slecht-geconfigureerde loader; geen exception
- Uitzonderingen: `force=True` overschrijft altijd -- bedoeld voor bootstrap-scenario, niet voor productie
