# Backend Feature Specification

## Metadata

- Feature ID: BE-AGT-017
- Feature naam: SP-AGT-005 Dag 3 -- _llm_critique structured JSON + MasterOrchestratorAgent.get_capabilities()
- Status: APPROVED
- Auteur: Claude (SP-AGT-005 Dag 3)
- Reviewer: subagent code-reviewer + quality-reviewer
- Datum: 2026-06-19
- Gerelateerde user story / ticket: SP-AGT-005 Dag 3
- Gerelateerde router / module: src/core/agents/critic_agent.py, src/core/agents/master_orchestrator_agent.py
- Gerelateerde frontend endpoints: N.v.t.
- Gerelateerde database tabellen: N.v.t. (in-memory CritiqueStore)
- Versie: 1.0

---

## Doel en scope

### Doel

Dag 3 sluit de laatste twee productiegaten van CriticAgent en MasterOrchestratorAgent:

1. `_llm_critique()` parste LLM-output via regex op vrije tekst. Bij elke LLM-afwijking werden
   score/issues/suggestions silently verkeerd geparsed. Fix: prompt omgezet naar JSON-only formaat
   + parser vervangen door `json.loads()` met score-clamping en isinstance-guards.

2. `MasterOrchestratorAgent.get_capabilities()` retourneerde een lege lijst. De agent was hierdoor
   onzichtbaar voor de UnifiedCapabilityRegistry. Fix: 3 concrete AgentCapability-objecten
   geretourneerd.

### In scope

- `_llm_critique()` in `src/core/agents/critic_agent.py`: JSON prompt + json.loads() parser
- `get_capabilities()` in `src/core/agents/master_orchestrator_agent.py`: 3 capabilities
- 7 nieuwe unit tests (TDD: rood voor, groen na)

### Out of scope

- CritiqueStore PostgreSQL persistentie (Dag 1)
- API endpoints voor critique reports (Dag 2)
- Config YAML voor CriticAgent (geen YAML-config aanwezig in codebase)

---

## Build summary

- Nieuw gebouwd: 2 testbestanden (7 tests)
- Gewijzigd: `src/core/agents/critic_agent.py` (import json + _llm_critique refactor), `src/core/agents/master_orchestrator_agent.py` (get_capabilities body)
- Verwijderd: Regex-gebaseerde tekstparser in _llm_critique() (~20 regels)
- Beinvloede bestaande flows: CriticAgent LLM-escalatiepad (heuristic score < 0.8 + use_llm=True)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-AGT-017a | _llm_critique() JSON parser | BE-AGT | src/core/agents/critic_agent.py | Wijziging | LLM critique escalatiepad |
| BE-AGT-017b | MasterOrchestratorAgent.get_capabilities() | BE-AGT | src/core/agents/master_orchestrator_agent.py | Wijziging | Capability registry |

---

## API-flows

### Flow 1: LLM Critique JSON escalatie

- Naam: CriticAgent LLM critique escalatie
- Trigger: `critique_task()` aangeroepen met `use_llm=True` en heuristic score < 0.8
- Voorwaarden: LLM client beschikbaar via `_get_llm_client()` (lazy-loaded provider)
- Request-pad: `_llm_critique(agent_name, result)` intern aangeroepen vanuit `critique_task()`
- Service-stappen:
  1. Haal LLM client op via `_get_llm_client()`
  2. Bouw JSON-only prompt met agent_name, output[:2000] en error
  3. Roep `llm.generate_response(prompt)` aan
  4. Check `response["success"]` -- bij False gooi RuntimeError
  5. Parseer `response["content"]` via `json.loads()`
  6. Clamp score: `max(0.0, min(1.0, float(parsed["score"])))`
  7. Filter issues/suggestions via isinstance(list) guard + str-cast
- DB-operaties: Geen
- Successtatus: tuple (score: float, issues: list[str], suggestions: list[str])
- Foutpaden:
  - `json.JSONDecodeError` / `ValueError` / `TypeError`: log warning met exc_info=True, return (0.5, [fallback], [fallback])
  - Exception op LLM-aanroep: log error met exc_info=True, return (0.5, [fallback], [fallback])
- Eindtoestand: Returnwaarden worden gecombineerd in critique_task() (weighted: 30% heuristic + 70% LLM)

### Flow 2: Capability registry opvragen

- Naam: MasterOrchestratorAgent capabilities
- Trigger: UnifiedCapabilityRegistry roept `get_capabilities()` aan op geregistreerde agents
- Voorwaarden: Geen auth vereist (interne agent-to-registry call)
- Service-stappen: Returneer lijst van 3 hardcoded AgentCapability-objecten
- DB-operaties: Geen
- Successtatus: `list[AgentCapability]` met 3 items
- Foutpaden: Geen (pure return)

---

## Detaildocumentatie per artefact

---

## [BE-AGT-017a] _llm_critique() JSON parser

### 1. Type

- AI-agent interne methode (LLM escalatie)

### 2. Locatie

- Bestandspad: `src/core/agents/critic_agent.py`
- Klasse / functie: `CriticAgent._llm_critique(agent_name: str, result: ExecutionResult) -> tuple[float, list[str], list[str]]`

### 3. Gerelateerde flow

- LLM critique escalatiepad (aangeroepen vanuit critique_task wanneer heuristic score < 0.8)

### 4. Doel

- Haal een gestructureerd JSON-oordeel op van een LLM over de kwaliteit van een agent-uitvoering
- Structureer score (0.0-1.0), issues en suggestions voor verdere verwerking

### 5. Functionele beschrijving

- Stuurt een JSON-only prompt naar de geconfigureerde LLM provider
- Verwerkt het antwoord als JSON om score, issues en suggestions te extraheren
- Valt terug op veilige defaults (score=0.5, fallback-tekst) bij parse-fouten
- Logt alle fouten met exc_info=True voor volledige stacktrace

### 6. Technische beschrijving

- `import json` toegevoegd aan stdlib-imports
- Prompt formaat: "Respond with exactly this JSON object and nothing else: {score, issues, suggestions}"
- Parser: `json.loads(response_text)` -- vervangt 20-regel regex tekstparser
- Score clamping: `max(0.0, min(1.0, float(parsed.get("score", 0.5))))`
- isinstance guard: `[str(i) for i in raw] if isinstance(raw, list) else []`
- Fallback bij `json.JSONDecodeError | ValueError | TypeError`: `logger.warning(..., exc_info=True)`
- Fallback bij outer Exception: `logger.error(..., exc_info=True)`

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: N.v.t. (interne methode, geen HTTP endpoint)
- Vereiste rol / scope: N.v.t.
- Tenant-isolatie: CriticAgent is per tenant gesingletonized (CriticAgent._instances[tenant_id])
- Feature flag: Alleen actief wanneer `use_llm=True` doorgegeven aan critique_task()

### 8. Request-specificatie

- Methode: Intern (Python method call)
- Signatuur: `async def _llm_critique(self, agent_name: str, result: ExecutionResult) -> tuple[float, list[str], list[str]]`
- Parameters: agent_name (naam van gecritiqueerde agent), result (ExecutionResult met output en error)

### 9. Response-specificatie

- Successtatus: tuple (score: float 0.0-1.0, issues: list[str], suggestions: list[str])
- Foutrespons: (0.5, ["LLM critique parse error -- please review manually"], ["Please review manually"])

### 10. Validaties en constraints

- Score wordt altijd geclampt naar [0.0, 1.0], ook bij out-of-range LLM output
- Output wordt afgekapt op 2000 tekens voor de prompt (DoS-preventie)
- issues en suggestions worden gefilterd: alleen als list, anders lege lijst

### 11. Business rules

- Score 0.5 is de neutrale fallback -- geen positieve of negatieve weging bij parse-fouten
- LLM-score telt 70% mee in de gewogen combinatie (heuristic 30%)
- Parse-fouten zijn non-fatal: critique_task() blijft functioneren

### 12. Afhankelijkheden

- `src/core/llm/provider_factory.get_llm_provider()` -- lazy-loaded
- `src/core/llm/llm_client.LLMClient.generate_response()` -- externe LLM API call

### 13. Foutafhandeling

- json.JSONDecodeError: warning log + fallback return
- ValueError / TypeError: warning log + fallback return
- Alle andere exceptions: error log + fallback return
- LLM success=False: RuntimeError -> outer exception handler -> error log + fallback

### 14. Transacties en dataïntegriteit

- Geen DB-schrijfoperaties in _llm_critique() zelf
- Resultaat wordt opgeslagen door critique_task() via CritiqueStore

### 15. Telemetry / logging / tracing

- `logger.warning("_llm_critique JSON parse failed: %s: %s", type(e).__name__, e, exc_info=True)`
- `logger.error("LLM critique failed: %s: %s", type(e).__name__, e, exc_info=True)`
- Geen f-strings in log calls (CLAUDE.md %s-patroon)

### 16. Caching

- Gecached: Nee
- Cache-sleutel: N.v.t.
- TTL: N.v.t.
- Invalidatie: N.v.t.

### 17. Acceptatiecriteria

- `test_llm_critique_parses_valid_json`: score=0.8, issues en suggestions correct geparsed
- `test_llm_critique_falls_back_on_bad_json`: score=0.5 en warning gelogd bij vrije tekst
- `test_llm_critique_tolerates_missing_keys`: score=0.7, issues=[], suggestions=[] bij ontbrekende keys
- `test_llm_critique_clamps_out_of_range_score`: score binnen [0.0, 1.0] bij score=999

### 18. Integratoruitleg

- _llm_critique() is een interne methode -- niet rechtstreeks aanroepbaar via API
- Activeer via critique_task() met use_llm=True
- Bij LLM-storingen: fallback score 0.5, geen exception, systeem blijft stabiel

### 19. Trainingssamenvatting

- Actor: CriticAgent (interne LLM-escalatie)
- Voorwaarde: use_llm=True en heuristic score < 0.8
- Actie (request): JSON-only prompt naar LLM provider
- Systeemverwerking: json.loads() parse + score clamping + isinstance guard
- Succesrespons: (float, list[str], list[str]) tuple
- Foutrespons: (0.5, [fallback], [fallback]) met warning/error log
- Uitzonderingen: LLM-timeout of -fout geeft fallback zonder te crashen

---

## [BE-AGT-017b] MasterOrchestratorAgent.get_capabilities()

### 1. Type

- AI-agent capability interface

### 2. Locatie

- Bestandspad: `src/core/agents/master_orchestrator_agent.py`
- Klasse / functie: `MasterOrchestratorAgent.get_capabilities() -> list[AgentCapability]`

### 3. Gerelateerde flow

- UnifiedCapabilityRegistry capability discovery

### 4. Doel

- Maakt MasterOrchestratorAgent zichtbaar voor de UnifiedCapabilityRegistry door 3 concrete
  AgentCapability-objecten te retourneren

### 5. Functionele beschrijving

- Retourneert 3 capabilities: workflow_orchestration, task_delegation, result_synthesis
- Enables capability-based routing naar de orchestrator door andere agenten en de registry

### 6. Technische beschrijving

- `AgentCapability` was al geimporteerd op regel 51 -- geen nieuwe imports
- 3 hardcoded capabilities met name, description, input_types, output_types, resource_requirements
- Veld `estimated_duration` weggelaten (optioneel veld, niet vereist voor registry)

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: N.v.t. (interne agent-to-registry call)
- Tenant-isolatie: N.v.t. (capabilities zijn tenant-onafhankelijk)

### 8. Request-specificatie

- Methode: Intern (Python async method call)
- Signatuur: `async def get_capabilities(self) -> list[AgentCapability]`

### 9. Response-specificatie

- Successtatus: `list[AgentCapability]` met 3 items (workflow_orchestration, task_delegation, result_synthesis)

### 10. Validaties en constraints

- Alle AgentCapability-velden zijn correct getypeerd (geen vrije dicts)

### 11. Business rules

- workflow_orchestration: primaire capability voor complexe multi-step taken
- task_delegation: routing van subtaken naar specialist agents
- result_synthesis: aggregatie van deelresultaten

### 12. Afhankelijkheden

- `src/core/shared/interfaces.AgentCapability` (Pydantic model)

### 13. Foutafhandeling

- Geen foutpaden (pure return van hardcoded objecten)

### 14. Transacties en dataïntegriteit

- Geen DB-operaties

### 15. Telemetry / logging / tracing

- Geen logging (pure return)

### 16. Caching

- Gecached: Nee

### 17. Acceptatiecriteria

- `test_get_capabilities_is_non_empty`: len(caps) >= 1
- `test_get_capabilities_includes_workflow_orchestration`: "workflow_orchestration" in namen
- `test_get_capabilities_returns_agent_capability_instances`: alle objecten zijn AgentCapability

### 18. Integratoruitleg

- De orchestrator is nu vindbaar via capability-gebaseerde matching
- Stuur taken van type "complex_task" of "multi_step_task" naar de orchestrator
- De registry routeert automatisch op basis van input_types

### 19. Trainingssamenvatting

- Actor: UnifiedCapabilityRegistry of delegerende agent
- Voorwaarde: Registry queried agents voor hun capabilities
- Actie (request): `await agent.get_capabilities()`
- Systeemverwerking: Return 3 hardcoded AgentCapability objecten
- Succesrespons: list[AgentCapability] met 3 items
- Foutrespons: N.v.t. (geen foutpaden)
- Uitzonderingen: N.v.t.

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

- `_llm_critique()` is intern -- gebruik `POST /critique/task` met `use_llm=True` om LLM-escalatie te activeren
- MasterOrchestratorAgent is nu vindbaar via capability-registry voor taken van type `complex_task` of `multi_step_task`
- Beide wijzigingen zijn backward compatible -- geen API-contractwijzigingen

---

## Open aannames

- LLM provider retourneert altijd `{"success": bool, "content": str}` formaat
- AgentCapability.estimated_duration is optioneel en niet vereist voor registry-registratie

## Open vragen

- Geen

## Risico's

- LLM providers die geen JSON retourneren (zelfs met JSON-only instructie): gedekt door fallback + warning log

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Alle foutstatus-codes getest (parse fallback, out-of-range score)
- [x] Auth en permissies getest (N.v.t. -- interne methoden)
- [x] Tenant-isolatie getest (via CriticAgent singleton per tenant_id)
- [x] Validaties getest (missing keys, bad JSON, out-of-range score)
- [x] Edge cases getest (score=999, lege JSON {}, vrije tekst)
- [x] Dataïntegriteit en transacties getest (N.v.t.)
- [ ] Performance / load getest (N.v.t. voor deze dag)
- [ ] Caching getest (N.v.t.)
- [x] Logging en tracing gecontroleerd (warning + error logs met exc_info=True)

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geinventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED
