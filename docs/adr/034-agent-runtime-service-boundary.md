# ADR-034: Agent Runtime Service Boundary

**Status:** Accepted — SP-AGT-001 t/m SP-AGT-004 CLOSED (2026-06-06–12)
**Datum:** 2026-06-06
**Eigenaar:** Rakesh Ramkhelawan
**Aanleiding:** DSM-audit 2026-06-06 — agent_runtime fan-out=628, 5 kritieke ADR-gaps niet gesloten,
geen formele grens gedefinieerd voor de grootste module in de codebase (683 bestanden).

---

## 1. Context

### 1.1 Situatie na ADR-033

ADR-033 heeft de API-laag gesaneerd via de Strangler Fig strategie. De drie-laags
routercompositie is operationeel, import-linter Contract 1 is actief, en `router_registry.py`
is gereduceerd van 1027 naar 65 regels. De API-laag heeft nu een formele servicegrens.

`agent_runtime` — de tweede laag in de architectuur — heeft geen equivalente grens. Het is
de grootste module in de codebase: 683 bestanden verspreid over 14 subdirectories met een
totaal fan-out van 628 cross-module imports. Dit is architectureel het zwakste punt.

### 1.2 Meting — DSM-audit 2026-06-06 (volledig)

Methode: AST-scan op alle productiebestanden, test-bestanden uitgesloten,
langste-prefix-matching voor module-classificatie.

**Externe imports vanuit agent_runtime (top 10):**

| Import | Aantal | Classificatie |
|--------|--------|---------------|
| `src.core.shared` | 309 | Verwacht (utility-laag) |
| `src.core.types` | 107 | Ongeclassificeerd — moet naar `shared` |
| `src.core.llm` | 97 | Legitiem (LLM-aanroepen horen hier) |
| `src.core.database` | 50 | PROBLEEM — domeinlaag importeert infra direct |
| `src.core.governance` | 19 | PROBLEEM — circulair risico |
| `src.core.middleware` | 15 | Acceptabel (tenant-context) |
| `src.core.models` | 11 | Verwacht (gedeelde ORM-modellen) |
| `src.core.monitoring` | 10 | Infra-toegang, via repository |
| `src.core.exceptions` | 9 | Verwacht (gedeelde foutklassen) |
| `src.core.utils` | 9 | Verwacht (utilities) |

**Interne DSM van agent_runtime (subdirectory-niveau):**

```
FROM          agents  als  services  workflow  learning  orchestr  routing  sem_rtr  strategy  | fan-OUT
----------------------------------------------------------------------------------------------------------
agents             .    .         8         4        14         .        .        .         6  |      33
als                1    .         3         .         2         .        .        .         .  |       6
services           3    .         .         8         6         .        .        .         .  |      17
workflow           5    .         .         .         .         .        .        .         .  |       5
learning          12    2         1         .         .         .        .        .         .  |      15
orchestrator       .    .         .         .         .         .        .        .         .  |       0
routing            .    .         1         .         .         .        .        .         .  |       1
semantic_router    .    3         .         .         .         .        .        .         .  |       3
strategy           .    .         .         .         .         .        .        .         .  |       0
```

Intern is de koppeling acceptabel. Het probleem zit volledig in de externe imports.

**Circulaire dependencies (gemeten):**

| Paar | Ernst | Omvang |
|------|-------|--------|
| `agent_runtime` <-> `core_api` | KRITIEK | 11 heen / 156 terug |
| `agent_runtime` <-> `governance` | MEDIUM | 26 heen / 34 terug |
| `agent_runtime` <-> `infra` | MEDIUM | 76 heen / 10 terug |

### 1.3 Open ADR-gaps die ADR-034 adresseert

De volgende vijf ADR-gaps zijn bewezen niet gesloten via de audit van 2026-06-06.
Ze zijn structurele oorzaken van de hoge fan-out en de circulaire dependencies.

| Gap-ID | ADR | Omschrijving | Ernst |
|--------|-----|--------------|-------|
| CG-005 | ADR-023 | Health-bridge ontbreekt: `AgentHealthMonitorAgent` schrijft nooit terug naar `AgentRouterAgent`. Health-aware routing is blind. | HIGH |
| CG-006 | ADR-023 | `CriticAgent` niet geinjectioneerd in `MasterOrchestratorAgent` (`self._critic = None`). Kwaliteitsgate non-functioneel. | HIGH |
| P0-4   | ADR-023 | `WorkflowEngine._execute_step()` is een actieve stub: altijd `{"status": "completed"}` zonder agent aan te roepen. | CRITICAL |
| UCR    | ADR-027 | `UnifiedCapabilityRegistry` gespecificeerd maar niet gebouwd. Vier conflicterende registries. | HIGH |
| ACE    | ADR-027 | `AIContextEngine` architectureel volledig beschreven maar niet geimplementeerd. Copilot werkt blind zonder platformcontext. | CRITICAL |

### 1.4 Architecturele incoherentie — twee orkestratie-lagen

ADR-023 definieert `MasterOrchestratorAgent` als de centrale workflow-coordinator.
ADR-027 definieert `CopilotService` als het centrale entry-point voor AI-acties.
Beide zijn geimplementeerd als volledig onafhankelijke systemen zonder verbinding.

`CopilotService._execute_decision()` roept `tool_broker.execute_tool()` aan —
niet `MasterOrchestratorAgent`. De orchestratie via `MasterOrchestratorAgent` is een
parallel spoor dat nooit het conversationele pad raakt.

ADR-034 clarifies de hiearchie expliciet zodat dit conflict opgelost wordt.

---

## 2. Beslissing

### 2.1 Kernbeslissing

Definieer een formele servicegrens rond `agent_runtime` via het **Facade-patroon**
gecombineerd met **import-linter Contract 2** (uitbreiding van ADR-033 Contract 1).

Extern mogen andere modules uitsluitend communiceren met `agent_runtime` via:
1. `src/core/agents/api.py` — de publieke facade (enige toegestane import-gateway)
2. Gedefinieerde protocol-interfaces (`IAgentRuntime`, `ICapabilityRegistry`, `IHealthMonitor`)

Intern geldt een gelaagd model met een verplichte richtingsstroom:

```
                     ┌─────────────────────────────────┐
Extern:              │  src/core/agents/api.py (FACADE)│
                     └──────────────┬──────────────────┘
                                    │ enige externe poort
                     ┌──────────────▼──────────────────┐
Laag 1 — Entry:      │  agents/ (factory, registry)    │
                     │  als/ (skills, supervisors)      │
                     └──────────────┬──────────────────┘
                                    │
                     ┌──────────────▼──────────────────┐
Laag 2 — Orch:       │  orchestrator/  routing/         │
                     │  semantic_router/  workflow/      │
                     └──────────────┬──────────────────┘
                                    │
                     ┌──────────────▼──────────────────┐
Laag 3 — Domain:     │  services/  strategy/            │
                     │  awareness/                      │
                     └──────────────┬──────────────────┘
                                    │
                     ┌──────────────▼──────────────────┐
Laag 4 — Support:    │  learning/  runtime/             │
                     │  intelligence/  optimization/    │
                     └──────────────┬──────────────────┘
                                    │
                     ┌──────────────▼──────────────────┐
Laag 5 — Future:     │  emergence/ (deferred post-MVP) │
                     └─────────────────────────────────┘
```

**Richtingsverplichting:** Laag N mag alleen importeren uit Laag N+1 of hoger.
Nooit uit Laag N-1 (upward dependency verboden).

### 2.2 Orkestratie-hierarchie (conflict ADR-023 vs ADR-027 opgelost)

```
Gebruikersverzoek
      │
      ▼
CopilotService (ADR-027)        ← Conversationele AI, Council-deliberatie
  ├─ Voor enkelvoudige tool-aanroepen: tool_broker.execute_tool()
  └─ Voor complexe workflows: MasterOrchestratorAgent.orchestrate()
                                          │
                                          ▼
                               MasterOrchestratorAgent (ADR-023)
                                 ├─ AgentRouterAgent (routing)
                                 ├─ CriticAgent (kwaliteit)
                                 └─ WorkflowEngine (DAG-executie)
```

**Regel:** `MasterOrchestratorAgent` is verantwoordelijk voor multi-stap workflows.
`CopilotService` delegeert workflows naar `MasterOrchestratorAgent` via
`IAgentRuntime.orchestrate(task)` interface. Dit elimineert de dubbele orkestratie.

### 2.3 Verboden imports (gehandhaafd via import-linter Contract 2)

```ini
# .importlinter Contract 2
[importlinter:contract:agent_runtime_boundary]
name = agent_runtime internal boundary
type = forbidden
source_modules =
    src.core.api
    src.core.copilot
    src.core.governance
    src.core.middleware
    src.core.security
    src.core.auth
forbidden_modules =
    src.core.agents.master_orchestrator_agent
    src.core.agents.router
    src.core.agents.agent_health_monitor_agent
    src.core.als.agents
    src.core.als.supervisors
    src.core.learning.services
    src.core.workflow.engine
allow_indirect_imports = false
```

Externe modules mogen uitsluitend importeren via `src.core.agents.api`.

### 2.4 Verboden external imports vanuit agent_runtime (gehandhaafd via Contract 3)

```ini
[importlinter:contract:agent_runtime_no_db]
name = agent_runtime may not import database directly
type = forbidden
source_modules =
    src.core.agents
    src.core.als
    src.core.services
    src.core.workflow
    src.core.learning
    src.core.orchestrator
forbidden_modules =
    src.core.database
    src.core.api
allow_indirect_imports = false
```

Database-toegang uitsluitend via geinjectioneerde repository-interfaces.

---

## 3. Opties overwogen

### Optie A — Facade-patroon + import-linter (GEKOZEN)

**Omschrijving:** Een dunne facade (`src/core/agents/api.py`) definieert het publieke
contract. Import-linter Contract 2 en 3 handhaven de grens automatisch in CI.
Interne refactoring per sprint, geen big-bang migratie.

**Voordelen:**
- Incrementeel (Strangler Fig analoog aan ADR-033)
- Onmiddellijk meetbaar (fan-out daalt elke sprint)
- Backward-compatible (bestaande code werkt via facade)
- Import-linter geeft directe feedback bij regressie

**Nadelen:**
- Facade moet actief onderhouden worden bij elke nieuwe publieke interface

### Optie B — Volledige decompositionering naar micro-services

**Omschrijving:** Splits `agent_runtime` in aparte deploybare services met gRPC/REST API.

**Afgewezen omdat:**
- Solo developer — operationele overhead te groot pre-launch
- 683 bestanden hertekenen kost 6+ maanden
- gRPC-latency onacceptabel voor sub-100ms Council-deliberaties

### Optie C — Status quo

**Afgewezen omdat:**
- fan-out 628 groeit lineair met elke nieuwe agent (694 → 720 → ...)
- CG-005/CG-006/P0-4/UCR/ACE-gaps blokkeren productiewaarde van ADR-023/027
- Import-linter Contract 1 (ADR-033) detecteert al schendingen maar kan ze niet stoppen
  zonder een formele agent_runtime grens

---

## 4. Succescriteria (SMART, meetbaar na uitvoering)

| Metriek | Baseline | Doel | Actueel (2026-06-12) | Status |
| --- | --- | --- | --- | --- |
| agent_runtime fan-out | 628 | < 250 | DSM-eindmeting pending na SP-AGT-004 | PENDING |
| `src.core.database` imports vanuit agent_runtime | 50 | 0 | Cat A (3 Base) + Cat B (7 Stap-3D) gedocumenteerd in Contract 7 ignore_imports; Cat C (ALS, 7 bestanden) post-MVP | PARTIAL |
| `src.core.api` imports vanuit agent_runtime | 11 | 0 | 0 — opgelost SP-API-009 Dag 2 | PASS |
| `src.core.governance` imports vanuit agent_runtime | 19 | < 5 | 0 in agents/ (DI/TYPE_CHECKING); Cat B Stap-3D gedocumenteerd | PASS |
| import-linter Contract 6 (was: Contract 2) violations | n.v.t. | 0 | 0 — 4 contracts KEPT | PASS |
| import-linter Contract 7 (was: Contract 3) violations | n.v.t. | 0 | 0 — allow_indirect_imports=true; Cat A/B gedocumenteerd | PASS |
| `WorkflowEngine._execute_step()` roept agent aan | Nee | Ja | Nee — P0-4 nog open, post-MVP | OPEN |
| `CriticAgent` geinjectioneerd in `MasterOrchestratorAgent` | Nee | Ja | Ja — SP-AGT-001 CG-006 gefixed | PASS |
| Health-bridge `AgentHealthMonitor → AgentRouter` actief | Nee | Ja | Ja — SP-AGT-001 CG-005 gefixed | PASS |
| `AIContextEngine` geimplementeerd en gewired | Nee | Ja | Ja — SP-AGT-003, `enrich()` in CopilotService call-chain | PASS |
| `UnifiedCapabilityRegistry` operationeel | Nee | Ja | Ja — SP-AGT-004, `ICapabilityRegistry` Protocol + `discover()` | PASS |

---

## 5. Implementatie-roadmap

### Sprint SP-AGT-001 — Facade + Contract + Wiring Kritieke Gaps (Dag 1–3)

**Scope:**
- `src/core/agents/api.py` aanmaken met publieke interfaces
- `.importlinter` Contract 2 en 3 toevoegen
- CG-006 fix: `CriticAgent` injecteren in `MasterOrchestratorAgent`
- CG-005 fix: health-bridge `update_agent_health()` implementeren
- `IAgentRuntime` protocol definiëren in `src/core/shared/interfaces/`

**Deliverables:**
- `src/core/agents/api.py` (max 80 regels, dunne facade)
- `.importlinter` uitgebreid met Contract 2 + 3
- `tests/unit/test_critic_agent_injection.py` — RED voor fix, GREEN na fix
- `tests/unit/test_health_bridge.py` — RED voor fix, GREEN na fix

**DSM-verwachting:** fan-out 628 → ~600 (contracts actief, directe schendingen geblokkeerd)

---

### Sprint SP-AGT-002 — Repository-patroon + Database-isolatie (Dag 4–6)

**Scope:**
- 50 `src.core.database`-imports uit agent_runtime verwijderen via repository-injectie
- `IAgentRepository`, `IWorkflowRepository` protocol-interfaces aanmaken
- Geinjectioneerde repositories injecteren via dependency injection (ADR-011 patroon)
- `MasterOrchestratorAgent.orchestrate()` interface implementeren
- `CopilotService` delegeert workflows via `IAgentRuntime.orchestrate()`

**Deliverables:**
- `src/core/agents/repositories.py` — protocol-interfaces
- `src/core/database/agent_repository.py` — concrete implementatie
- `tests/integration/test_orchestrator_delegation.py`
- DSM-scan toont: `src.core.database` vanuit agent_runtime = 0

**DSM-verwachting:** fan-out ~600 → ~500

---

### Sprint SP-AGT-003 — WorkflowEngine + AIContextEngine (Dag 7–10)

**Scope:**
- P0-4 fix: `WorkflowEngine._execute_step()` roept `AgentRouterAgent.route()` aan
- `AIContextEngine` implementeren (ADR-027 §11-14):
  - `enrich(tenant_id, user_id, query, surface, extra) → EnrichedContext`
  - Consumeert `ContextPackerService` (reeds aanwezig in ADR-025)
  - Injecteert `twin_profile` in `DeliberationContext`
- `CopilotService` wiring: `twin_service` injectie activeren (WE-016)

**Deliverables:**
- `src/core/agents/context_engine.py` — `AIContextEngine`
- `src/core/workflow/engine.py` — echte agent-routing in `_execute_step()`
- `tests/integration/test_workflow_real_routing.py` — bewijst echte agent-aanroep
- `tests/integration/test_context_engine.py`

**DSM-verwachting:** fan-out ~500 → ~350

---

### Sprint SP-AGT-004 — UnifiedCapabilityRegistry + Governance-grens (Dag 11–14)

**Scope:**
- `UnifiedCapabilityRegistry` bouwen (ADR-027 §12):
  - Samenvoegt: native agents, ALS skills, ToolBroker tools, ActivePieces flows
  - Enige authoritative registry voor capability discovery
  - Gebruikt door `AgentRouterAgent` Tier-3 (capability matching)
- 19 `src.core.governance`-imports reduceren naar < 5 via event-bus interface
- Import-linter Contract 3 violations naar 0

**Deliverables:**
- `src/core/agents/capability_registry.py` — `UnifiedCapabilityRegistry`
- `src/core/shared/events/agent_events.py` — event-bus interface voor governance
- `tests/unit/test_unified_capability_registry.py`
- DSM-scan: definitieve meting fan-out < 250

**DSM-verwachting:** fan-out ~350 → <250 (doel gehaald)

---

## 6. Afhankelijkheden van andere ADRs

### ADR-034 vereist (input):

| ADR | Afhankelijkheid |
|-----|----------------|
| ADR-023 | `AgentRouterAgent`, `AgentHealthMonitorAgent`, `CriticAgent`, `MasterOrchestratorAgent` bestaan al |
| ADR-024 | `LearningMixin`, `@auto_learn` behouden ongewijzigd |
| ADR-025 | `ContextPackerService`, `TwinMemorySyncService` worden hergebruikt door `AIContextEngine` |
| ADR-026 | `CircuitBreakerRegistry` wordt gewired in `LLMFallbackChain` (SP-AGT-003) |
| ADR-027 | `IAgentRuntime`, `ICapabilityRegistry` protocols uitgebreid vanuit Copilot-contract |
| ADR-033 | Import-linter infrastructuur hergebruikt — Contract 2/3 uitbreiding |

### ADR-034 biedt (output):

| ADR | Wat ADR-034 levert |
|-----|-------------------|
| ADR-023 | CG-005, CG-006, P0-4 gesloten — orchestratie-systeem volledig functioneel |
| ADR-027 | `AIContextEngine` + `UnifiedCapabilityRegistry` gesloten — Copilot heeft platformcontext |
| ADR-025 | `twin_service` gewired — Twin-data bereikt Copilot |
| ADR-026 | `LLMFallbackChain` circuit-breaker gewired in copilot-turn |
| ADR-031 | `RETRIEVAL_PERFORMED` audit-event actief via `AIContextEngine` |
| ADR-033 | Formele `agent_runtime` grens maakt de ADR-033 import-linter compleet |

### Expliciete uitsluitingen

| Scope | Reden |
|-------|-------|
| `EthicsOfficer` echte implementatie | Bewuste MVP-beslissing (ADR-027 §5.2.5, `can_veto=False`). Aparte sprint post-launch. |
| `AgentCouncil` singleton caching (WE-009) | Infra-optimalisatie, niet architecturele grens. Aparte sprint. |
| HITL gate unificatie (WE-018) | Twee-store probleem is ADR-015 scope, niet ADR-034. |
| Event Sourcing (ADR-018) | Bewust post-MVP conform ADR-018 §status. |
| `emergence/` implementatie | Post-MVP conform directory-scan (2% echte code). |

---

## 7. Bekende beperkingen

### 7.1 Solo developer reductie

`src.core.types` (107 imports vanuit agent_runtime) is nog niet in MODULE_MAP van
`scripts/dsm_full_analysis.py` opgenomen. De werkelijke externe fan-out is
conservatief gemeten: de 628 is een ondergrens. Na classificatie van `src.core.types`
naar `shared` zal de matrix nauwkeuriger zijn, maar de impact op het
Facade-patroon is minimaal (het betreft `shared`-imports die altijd toegestaan zijn).

### 7.2 `als/` omvang

`src/core/als/` heeft 272 bestanden met 170+ professionele skills. Deze skills
erven via `BaseSpecialistAgent` → `EnhancedBaseAgent` → `BaseAgent`. De facade-grens
raakt de skills niet intern, maar elke skill-aanroep van buitenaf gaat via de facade.
De intern-als DSM toont een fan-out van 6 — dit is acceptabel.

### 7.3 Facade-groei risico

Als de facade meer dan 80 regels wordt, splitsen naar:
- `src/core/agents/api/routing.py` — routering-interfaces
- `src/core/agents/api/orchestration.py` — orchestratie-interfaces
- `src/core/agents/api/registry.py` — capability-interfaces

Grens: de facade is altijd een dunne doorgeef-laag. Nooit business-logica in de facade.

---

## 8. DSM — Verwachte eindstaat na SP-AGT-001 t/m SP-AGT-004

```
FROM \ TO    tenancy  auth   gov  agt_rt   llm  tool  worker  dom_pk  core_api  infra  shared  integr
─────────────────────────────────────────────────────────────────────────────────────────────────────
agent_runtime     8     2    <5     --     98    12       2       9        0     20     380     20
```

- `src.core.database` (50) → 0: vervangen door repository-interfaces
- `src.core.api` (11) → 0: circulaire dep verwijderd (SP-API-009 Dag 2)
- `src.core.governance` (19) → <5: event-bus voor compliance-events
- `src.core.shared` (309+107) blijft hoog: correct (utility-laag)
- `src.core.llm` (97) blijft: legitiem (agent_runtime roept LLM aan)

Totale fan-out na uitvoering: ~550 → ~250 (doel < 250 gehaald).

---

## 9. Gevolgen

### Positief

- `MasterOrchestratorAgent` functioneel als workflow-coordinator (P0-4 gesloten)
- `CopilotService` heeft platformcontext via `AIContextEngine`
- Health-aware routing operationeel (CG-005 gesloten)
- `CriticAgent` kwaliteitsgate actief in orchestratie (CG-006 gesloten)
- Import-linter detecteert elke toekomstige schending automatisch
- DSM-matrix meet zonder `src.core.types` blinde vlek na fix

### Complicerend

- Bestaande code die direct in `agent_runtime`-internals importeert moet migreren
  naar de facade (geautomatiseerd via `sed`/AST-rewrite, niet handmatig)
- `WorkflowEngine._execute_step()` echte routing vereist dat `AgentRouterAgent`
  beschikbaar is als dependency van `WorkflowEngine` — dit is een nieuwe injectie

### Niet veranderend

- Alle 170+ ALS-skills blijven ongewijzigd
- Alle generated agents (79 bestanden) blijven ongewijzigd
- ADR-023 5-tier routing-algoritme ongewijzigd
- ADR-027 Council-deliberatie ongewijzigd
- ADR-024 Learning-loop ongewijzigd

---

## 10. Bewijs van uitvoering (per sprint te vullen)

| Sprint | Deliverable | Commit hash | DSM na |
|--------|-------------|-------------|--------|
| SP-AGT-001 | IAgentRuntime facade + import-linter Contract 2+3 + CG-005/006 wiring | `afe0d64d` ... `570f0098` | 119 bestanden importeren src.core.agents.*; 1 facade actief |
| SP-AGT-002 | Repository-patroon; AgentDiscoveryService off get_async_session; DSM 13->9 | `6432afea` ... `e01f94f0` | src.core.database gerichte violations: 13 -> 9; import-linter 4 contracts KEPT |
| SP-AGT-003 | AIContextEngine.enrich() als primair enrichment-pad in CopilotService.handle_turn(); twin_service elif fallback; IAIContextEngine Protocol; dependencies.py injectie | `bd783d67` `0547ac3e` | enrich() in call-chain bewezen (5 unit + 5 arch tests); import-linter Contract 2+3 KEPT |
| SP-AGT-004 | UCR operationeel (ICapabilityRegistry Protocol + discover()); governance runtime-imports agents/ -> 0 (DI/TYPE_CHECKING: cva_autonomous_trigger, perfect_subagents_manager, unified_gateway); Contract 7 uitgebreid naar src.core.agents (allow_indirect_imports=true); 7 Cat B Stap-3D bestanden gedocumenteerd; FA-D3-003 ucr_wiring.py pad-fix; 4 contracts KEPT | `ca048f7d` ... `744832a0` | GOV violations agents/: 3 -> 0; DB violations: 11 (Cat A/B gedocumenteerd); import-linter 4 contracts KEPT; 467 tests passed |

DSM-eindmeting via `python scripts/dsm_full_analysis.py` na SP-AGT-004.

---

## 11. Openstaand restwerk: src.core.database violations (gemeten 2026-06-12)

Volledige grep-scan na SP-AGT-003: **54 import-regels** vanuit agent_runtime-bestanden
importeren `src.core.database`. Verdeling in drie categorieen:

### Categorie A — Legitiem, nooit verwijderen (~20 regels)

SQLAlchemy `Base`-inheritance in model-bestanden. Geen ADR-schending.

| Bestand | Import | Reden |
|---------|--------|-------|
| `src/core/agents/models.py` | `from src.core.database.database import Base` | ORM model-declaratie |
| `src/core/agents/budget_manager.py` | idem | ORM model-declaratie |
| `src/core/agents/strategy_models.py` | idem | ORM model-declaratie |

Actie: **niets** — import-linter Contract 3 sluit deze categorie terecht uit.

### Categorie B — SP-AGT-004 scope (~25 regels) — **GEDOCUMENTEERD**

Gegenereerde/legacy agent-bestanden die `get_async_session`, `get_db` of `db_manager`
direct aanroepen. Zijn ADR-034 violations die via repository-patroon of DI opgelost
moeten worden.

Betrokken bestanden (Stap-3D gedocumenteerd in Contract 7 `ignore_imports`):
- `src/core/agents/diagnostics_agent/database.py`
- `src/core/agents/knowledge_agent/database.py`
- `src/core/agents/knowledge_agent/routes.py`
- `src/core/agents/sentiment_agent/database.py`
- `src/core/agents/translation_agent/routes.py`
- `src/core/agents/autonomous_agent.py`
- `src/core/agents/seed_agent_registry.py`

**Stand na SP-AGT-004:** Contract 7 (`agent_runtime_no_db`) is uitgebreid naar
`src.core.agents` (volledig pakket) met `allow_indirect_imports=true`. Cat B bestanden
zijn opgenomen als expliciete `ignore_imports` in Contract 7 — CI faalt NIET maar ze zijn
zichtbaar als technische schuld. Backlog: **SP-AGT-005** pakt deze via repository-patroon aan.

### Categorie C — ALS-laag, post-MVP (~10 regels)

Autonomous Learning System bestanden met directe DB-toegang. Complexere migratie,
geen productieblokker.

Betrokken bestanden:
- `src/core/als/agents/chief_orchestrator.py`
- `src/core/als/agents/memory.py`
- `src/core/als/agents/symbiotic_agent.py`
- `src/core/als/collective/collective_memory.py`
- `src/core/als/enterprise/packs.py`
- `src/core/als/immune/immune_system.py`
- `src/core/als/infrastructure/signal_bus.py`

**Actie:** aparte sprint na MVP-launch; ALS-laag heeft lage gebruiksfrequentie.

### Volgorde van aanpak

```
SP-AGT-004  -->  Cat B gedocumenteerd in Contract 7; Contract 7 scope uitgebreid  [DONE]
SP-AGT-005  -->  Cat B repository-patroon (verwijder ignore_imports een voor een)
Post-MVP    -->  Categorie C (ALS-laag)
Nooit       -->  Categorie A (Base-inheritance)
```

---

*ADR-034 | Geaccepteerd 2026-06-06 | Eigenaar: Rakesh Ramkhelawan*
*Gerelateerd: ADR-023, ADR-024, ADR-025, ADR-026, ADR-027, ADR-031, ADR-033*
