# BE-AGT-030: IAgentRuntime Facade + import-linter Contract 2+3

**Sprint:** SP-AGT-001 Dag 1
**ADR:** ADR-034 (agent_runtime service boundary)
**Status:** IMPLEMENTED
**Datum:** 2026-06-09

---

## Samenvatting

`src/core/agents/api.py` is aangemaakt als de enige publieke toegangspoort voor
`agent_runtime`. Externe modules importeren uitsluitend via dit bestand.

Drie runtime-checkable Protocols gedefinieerd:
- `IAgentRuntime` -- facade voor `orchestrate`, `route`, `get_health`
- `ICapabilityRegistry` -- interface voor capability discovery (SP-AGT-004)
- `IHealthMonitor` -- health-bridge write interface (CG-005)

Twee lazy singletons met `register_*()`/`get_*()` accessor functions voor app-lifespan wiring.

import-linter Contract 6 (`agent_runtime_boundary`) en Contract 7 (`agent_runtime_no_db`)
bewaken dat de facade zelf geen circulaire afhankelijkheden krijgt.

---

## Gewijzigde bestanden

| Bestand | Wijziging |
|---------|-----------|
| `src/core/agents/api.py` | Nieuw: facade met 3 Protocols + 4 accessor functions |
| `.importlinter` | Contract 6 + 7 toegevoegd (facade boundary + geen directe DB) |
| `tests/unit/agents/test_agents_facade.py` | Nieuw: 6 TDD tests (module, exports, max-lines, Protocol check, orchestrate) |
| `tests/architecture/test_adr034_contracts.py` | Nieuw: 3 tests (contract aanwezig, geen parse-errors) |

---

## Architectuurbeslissingen

### A: Protocols in api.py, niet in shared/interfaces.py

`src.core.workflow.interfaces` heeft al een `IAgentRuntime` ABC met andere methoden.
Naming collision vermeden door de ADR-034 Protocols direct in de facade file te definieren.
Externe code importeert uitsluitend via `src.core.agents.api`.

### B: Contract 2+3 narrowed scope (Dag 1)

Contract 6 en 7 bewaken alleen `src.core.agents.api` zelf. Bredere enforcement
(externe modules moeten via facade gaan) is progressieve migratie in SP-AGT-002+.

### C: Lazy singletons per Gunicorn worker

Module-level singletons zijn process-local. Elke Uvicorn worker registreert zijn eigen
instantie via `register_agent_runtime()` in app lifespan. Thread-safety: asyncio
single-threaded event loop per worker; geen concurrent-write risico.

---

## Testresultaten

- Targeted (agents + architecture): 368 passed, 0 failed
- Full unit suite: 12690 passed, 0 failed, 236 skipped, 20 xfailed


## Trainingssamenvatting

- Actor: Een ontwikkelaar of app-lifespan functie die de agent-runtime facade gebruikt.
- Voorwaarde: `src/core/agents/api.py` is geimporteerd; bij gebruik van `get_agent_runtime()` moet eerst een implementatie zijn geregistreerd via `register_agent_runtime()`.
- Actie (request): Roep `register_agent_runtime(runtime: IAgentRuntime)` aan om een concrete runtime te registreren, of `get_agent_runtime()` / `get_health_monitor()` om de geregistreerde instantie op te halen.
- Systeemverwerking: De module bewaart de instantie in een module-level singleton (`_agent_runtime_instance` of `_health_monitor_instance`). `register_agent_runtime()` logt een warning als er al een instantie bestaat en overschrijft deze. `get_agent_runtime()` retourneert de instantie; `get_health_monitor()` retourneert `None` als er niets is geregistreerd.
- Succesrespons: `get_agent_runtime()` geeft het geregistreerde `IAgentRuntime`-object terug; `register_agent_runtime()` logt `"agent_runtime registered: <klasse>"`.
- Foutrespons: `get_agent_runtime()` gooit `RuntimeError("agent_runtime not registered...")` als er geen instantie is geregistreerd.
- Uitzonderingen: Herhaalde registratie is toegestaan maar genereert een waarschuwing; gezondheidsmonitor is optioneel (`None`) terwijl runtime verplicht is.
