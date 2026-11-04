# ADR-027: Co-Pilot met Agent Council voor Compliance & Veiligheid

## Status

Accepted — 2026-05-23 (sprint 2 dag 5); Governance program completed — 2026-05-26

### Statushistorie
- 2026-05-22: Proposed (initiële opstelling, sprint 1 start)
- 2026-05-23: Accepted (na E2E validatie met 7 echte Officers, P95 < 500ms,
  tenant isolatie bewezen via RLS-tests, hash chain integriteit bewezen
  over 1000 sequentiële decisions)
- 2026-05-24: Sprint 3 productie-hardening afgerond (chaos tests, Redis cache,
  observability stack, security audit, OpenAPI documentatie, runbooks)
- 2026-05-24: Sprint 4 dag 1 afgerond — CopilotService.handle_turn,
  LLMHandler (JSON-mode + 1x retry), ProposalBuilder, Pydantic schemas,
  Protocol interfaces (IToolBroker, ITwinService, IHITLRepository),
  LLMClient.complete_json met provider overrides (DeepSeek, Gemini, Anthropic)
- 2026-05-26: ADR-031 platform-wide governance program completed — 6 sprints,
  30 evidence records, 40/40 matrix routes closed, all P0 gaps resolved,
  program GO for EU AI Act 2 augustus 2026 deadline

## Context

De Co-Pilot van SanskritiSetu is in de huidige codebase versnipperd over drie endpoints (`POST /api/v1/intents/parse`, `POST /api/v1/ai-copilot/suggest-tools`, `WS /ws/copilot/chat`), met dubbele NLU-paden en mock-implementaties op kritieke punten (zie audit `docs/copilot-feature-context.md`, 2026-05-22). Tegelijk is de Co-Pilot strategisch het belangrijkste contactpunt tussen de gebruiker en het platform: hij moet alle routes en functionaliteiten kennen, proactief signalen geven, en samenwerken met de Digital Twin (ADR-025, ADR-026).

Per **2 augustus 2026** wordt de **EU AI Act Artikel 12** afdwingbaar: high-risk AI-systemen moeten elke gebeurtenis automatisch loggen met actor, tijdstempel, model, uitkomst en de reasoning. **Artikel 13** vereist transparantie voor deployers; **Artikel 50** verplicht dat eindgebruikers weten dat zij met een AI praten. Naast de AI Act zijn **GDPR Artikel 22** (geen volledig geautomatiseerde besluitvorming zonder menselijke tussenkomst) en **ISO 42001 A.6.2.8** (event logging requirements) van toepassing.

SanskritiSetu heeft losse compliance-modules:

| Module | Bestand | Functie |
|--------|---------|---------|
| Compliance Guardian | `src/core/governance/compliance_guardian.py` | EU AI Act / GDPR rule checks |
| GDPR Enforcer | `src/core/governance/gdpr_enforcer.py` | Persoonsgegevens, consent |
| Policy Engine | `src/core/governance/policy_engine.py` | Tenant-policy enforcement |
| Oversight Gate | `src/core/governance/oversight_gate.py` | HITL escalation |
| Risk Register | `src/core/governance/risk_register.py` | Risk severity |
| Ethics Gate | `src/core/ethics/ethics_gate.py` | Ethics check skeleton |
| Rate Limiter | `src/core/governance/rate_limiter.py` | Resource throttling |
| Hash Chain | `src/core/governance/hash_chain.py` | Tamper-evident audit (ADR-019) |
| AI Act Classifier | `src/core/governance/ai_act_classifier.py` | High-risk classification |
| AI Transparency Service | `src/core/governance/ai_transparency_service.py` | Right-to-explanation API |

Deze modules werken **onafhankelijk** en worden ad-hoc aangeroepen vanuit verschillende routes. Er is geen coördinerende laag die garandeert dat voor elke AI-actie (proactief of reactief) **alle** relevante checks doorlopen worden en in **één auditeerbare beslissing** worden samengebracht.

### Probleem in één zin

Wij hebben alle compliance-bouwstenen maar geen formeel orgaan dat ze samenbrengt per AI-beslissing — wat per 2 augustus 2026 een wettelijk vereiste wordt en commercieel een unieke verkooppropositie kan zijn.

### Alternatieven

| Optie | Voordeel | Nadeel | Besluit |
|-------|----------|--------|---------|
| **A. Status quo (losse modules per call site)** | Geen extra code | Geen garantie dat alle checks doorlopen worden; niet AI Act compliant; geen consistente audit | Afgewezen |
| **B. Eén monolithische `ComplianceService` voor alle Co-Pilot calls** | Simpel, één entry point | Niet uitbreidbaar; geen scheiding van zorgen; bias-checks vermengd met token-budget-checks | Afgewezen |
| **C. Agent Council met 7 Officers + Coordinator** | Scheiding van zorgen; uitbreidbaar; mapping op bestaande modules; sterke audit-trail; verkoopbaar als feature | Extra coördinatielaag (~50-150ms per beslissing) | **Gekozen** |
| **D. Per-tenant configureerbare compliance pipeline (DAG)** | Maximale flexibiliteit | Te complex voor MVP; risico op tenant misconfiguratie die compliance breekt | Fase 2+ |

## Decision

Wij implementeren een **Agent Council** als verplichte beslissingslaag voor elke Co-Pilot-actie (proactief én reactief). De Council is een coördinator over zeven gespecialiseerde "Officers", waarvan vijf bestaande modules herbestemmen en twee nieuw worden gebouwd. Elke beslissing wordt vastgelegd in de bestaande hash-keten (ADR-019), uitgebreid met AI Act-velden.

### 1. De zeven Officers

| # | Officer | Verantwoordelijkheid | Macht | Implementatie |
|---|---------|---------------------|-------|---------------|
| 1 | **ComplianceOfficer** | EU AI Act art. 12/13/50, GDPR, ISO 42001 | `VETO` | Wraps `compliance_guardian.py` + `ai_act_classifier.py` |
| 2 | **PrivacyOfficer** | Persoonsgegevens, consent, cross-sessie geheugen | `VETO` | Wraps `gdpr_enforcer.py` + `practical_twin_service.consent_gate` (ADR-026) |
| 3 | **SecurityOfficer** | Tool-allowlist, prompt injection, scope-validatie | `VETO` | Wraps `tool_broker` (ADR-015) + `PromptGuard` (ADR-015 P0-6) |
| 4 | **RiskOfficer** | Impact-classificatie, HITL-escalatie | `REQUIRE_HITL` | Wraps `risk_register.py` + `ShadowCEO` (ADR-016) |
| 5 | **EthicsOfficer** | Bias, fairness, transparantieplicht | `REQUIRE_MODIFICATION` | **NIEUW** — bouwt op `ethics_gate.py` skeleton |
| 6 | **ResourceOfficer** | Token-budget, rate limits, notificatie-budget (25/dag), kosten | `DEFER` | **NIEUW** — bouwt op `rate_limiter.py` + Prana Economy (ADR-021) |
| 7 | **AuditOfficer** | Tamper-evident logging conform AI Act art. 12 | `LOG_ONLY` (kan niets blokkeren) | Wraps `hash_chain.py` + `governance/audit.py` (ADR-019) |

### 2. Verdict types

Elke Officer geeft per voorstel één van vier verdicts terug:

```python
class VerdictType(str, Enum):
    APPROVE = "approve"                  # Geen bezwaar
    APPROVE_WITH_MODIFICATION = "modify" # Goedkeuren mits aanpassing (alleen Ethics, Compliance)
    REQUIRE_HITL = "require_hitl"        # Vereist menselijke goedkeuring (Risk, Privacy soms)
    REQUIRE_DEFERRAL = "defer"           # Uitstel: nu niet, later opnieuw proberen (Resource)
    VETO = "veto"                        # Definitieve blokkade (Compliance, Privacy, Security)
```

### 3. Aggregatie-regels

De Coordinator past **strikt-de-hoogste-eis** logica toe:

```
ALS één Officer VETO geeft:
    eindbesluit = BLOCKED
ANDERS ALS minstens één Officer REQUIRE_HITL geeft:
    eindbesluit = HITL_REQUIRED → escaleert via OversightGate
ANDERS ALS minstens één Officer REQUIRE_DEFERRAL geeft:
    eindbesluit = DEFERRED → planner herprobert
ANDERS ALS minstens één Officer APPROVE_WITH_MODIFICATION geeft:
    eindbesluit = MODIFIED → Co-Pilot past voorstel aan en herziet
ANDERS:
    eindbesluit = APPROVED
```

De AuditOfficer wordt **altijd als laatste** geconsulteerd. Hij blokkeert nooit, maar schrijft het volledige beraadslagingsverslag naar de hash-keten. Geen audit log = geen executie (fail-secure).

### 4. Proposal-formaat (input van Co-Pilot naar Council)

```python
@dataclass(frozen=True)
class Proposal:
    proposal_id: UUID                    # Uniek per voorstel
    tenant_id: int                       # Uit JWT (ADR-003)
    user_id: int                         # Uit JWT
    trigger: ProposalTrigger             # PROACTIVE_MONITOR | USER_REQUEST | DIGITAL_TWIN_SUGGESTION
    action_type: str                     # "send_notification", "navigate_to", "execute_workflow", etc.
    action_params: dict[str, Any]        # Tool-specifieke parameters
    reasoning: str                       # Natuurlijke taal: waarom stelt Co-Pilot dit voor?
    data_classification: DataClassification  # PUBLIC | INTERNAL | CONFIDENTIAL | RESTRICTED (ADR-019)
    confidence: float                    # 0.0-1.0, LLM-confidence
    model_id: str                        # bv. "deepseek-chat-v3.1"
    model_version: str                   # Voor reproduceerbaarheid
    context_snapshot: dict[str, Any]     # Route, page, recent actions
    timestamp: datetime                  # timezone-aware UTC (CLAUDE.md regel 3)
```

### 5. CouncilDecision (output van Council)

```python
@dataclass(frozen=True)
class CouncilDecision:
    decision_id: UUID
    proposal_id: UUID
    tenant_id: int
    verdict: DecisionVerdict             # APPROVED | MODIFIED | HITL_REQUIRED | DEFERRED | BLOCKED
    officer_verdicts: list[OfficerVerdict]  # Per officer: verdict + reden + evidence
    modifications: dict[str, Any] | None # Bij MODIFIED: welke params zijn aangepast
    hitl_request_id: UUID | None         # Bij HITL_REQUIRED: koppelt naar OversightGate
    explanation_for_user: str            # GDPR art. 13-15 right-to-explanation
    decision_hash: str                   # SHA-256 ketenschakel
    previous_decision_hash: str          # Vorige beslissing per tenant
    deliberation_ms: int                 # Latentie meten voor SLA
    timestamp: datetime
```

### 6. Hash chain extensie (AI Act compliant)

ADR-019 introduceerde een SHA-256 hash chain voor governance events. Wij breiden het schema uit zonder de bestaande keten te breken:

```python
# Bestaande velden (ADR-019, ADR-017)
"decision_id", "timestamp", "task_id", "tenant_id", "decision", "previous_hash"

# Nieuwe velden voor AI Act art. 12 conformiteit
"proposal_id"           # Koppeling naar AI-voorstel
"model_id"              # Welk model heeft de input geproduceerd
"model_version"         # Reproduceerbaarheid
"reasoning_chain"       # Co-Pilot reasoning + Officer reasoning
"data_classification"   # PUBLIC/INTERNAL/CONFIDENTIAL/RESTRICTED
"explanation_summary"   # Korte uitleg voor right-to-explanation
"officer_verdicts_hash" # SHA-256 over alle officer-uitspraken
```

### 7. Bewaartermijn

Conform `CLAUDE.md` aangevulde besluit van gebruiker (2026-05-22): **13 maanden** voor alle Council-besluiten en bijbehorende Co-Pilot reasoning chains. Implementatie via bestaande `retention_cleanup.py` (uitbreiding van retention-policy tabel).

| Data-type | Bewaartermijn | Wettelijke basis |
|-----------|---------------|------------------|
| Council decisions (hash chain) | 13 maanden | EU AI Act art. 26(6) — minimum 6, wij kiezen 13 |
| Officer reasoning (natuurlijke taal) | 13 maanden | GDPR art. 13-15 right-to-explanation |
| Notification dispatch log | 90 dagen | Operationeel |
| User notification preferences | Tot DSAR / accountverwijdering | GDPR art. 6 |

### 8. Notificatie-budget

Standaard **25 ongevraagde notificaties per gebruiker per dag**, instelbaar tussen 0 en 100 met "dagelijkse samenvatting" als alternatief (smart batching). De ResourceOfficer bewaakt deze grens; bij overschrijding krijgt het voorstel `DEFER` (verschuift naar de volgende dag, kritieke meldingen uitgezonderd).

### 9. Co-Pilot consolidatie

Parallel aan de Council-bouw worden de drie versnipperde Copilot-endpoints geconsolideerd tot één service:

- `POST /api/v1/copilot/turn` — one-shot interactie (Cmd+K, focus-builder), optioneel SSE
- `WS /ws/copilot/chat` — multi-turn streaming chat (sidebar)
- `POST /api/v1/copilot/proactive/{signal_id}/respond` — gebruiker reageert op proactief signaal

Alle drie routes lopen langs de **CopilotService**, die voor elke beslissing een `Proposal` opbouwt en de Council consulteert vóór uitvoering.

### 10. Verplichte AI Act transparantie

Conform art. 50: elke Co-Pilot UI-component toont een persistente "AI-aanwezigheid" indicator (klein icoon, bv. links onderin het scherm) plus een tooltip "Dit is een AI-assistent". Bij elke proactieve melding wordt de bron (Co-Pilot) expliciet vermeld. Bij elke geboden uitleg verwijst een link naar de AuditViewer waar de gebruiker het volledige Council-besluit kan inzien (right-to-explanation, GDPR art. 13-15).

## Consequences

### Positive

- **Wettelijke conformiteit by design** — EU AI Act art. 12, 13, 50 + GDPR art. 22 + ISO 42001 A.6.2.8 worden architectonisch afgedwongen, niet ad-hoc.
- **Verkoopbare propositie** — "Built-in AI Council met audit trail voor elke beslissing" is een unieke positie in de EU-markt vanaf 2 augustus 2026.
- **Centrale auditeerbaarheid** — één locatie (de hash-keten) bevat élke AI-beslissing van het platform. Externe audits worden triviaal.
- **Hergebruik van bestaande modules** — 5 van 7 Officers wrappen bestaande code; geen herbouw van compliance, GDPR, risk of audit.
- **Scheiding van zorgen** — bias-checks, kosten-checks en privacy-checks zitten in aparte Officers, individueel testbaar.
- **Right-to-explanation API uit de doos** — `explanation_for_user` veld per beslissing voorzien.
- **Toekomstvast** — nieuwe regelgeving (bv. AI Liability Directive) kan via een achtste Officer worden toegevoegd zonder bestaande code te raken.

### Negative

- **Latentie** — geschatte 50-150ms extra per Co-Pilot beslissing door 7-officer beraadslaging. Mitigatie: parallel uitvoering (asyncio.gather), Redis-caching van deterministische officer-uitspraken.
- **Coördinatiecomplexiteit** — orchestratie van 7 modules met aggregatieregels vereist zorgvuldige testdekking (Coordinator alleen al krijgt ~60 unit tests + 10 integration tests).
- **Nieuwe twee Officers** — Ethics en Resource Officer moeten van scratch worden gebouwd (geschat 2 sprint-weken samen).
- **Fail-secure overhead** — als de AuditOfficer faalt, wordt het hele voorstel geblokkeerd. Vereist robuuste audit-write met `best_effort` of expliciete fallback.

### Mitigations

- **Parallel beraadslaging** — `asyncio.gather(*officer_tasks)` zodat alle Officers tegelijk hun verdict berekenen. Latentie wordt dominant door langzaamste Officer (meestal Compliance bij LLM-classificatie).
- **Cache deterministische uitspraken** — Security/Resource/Privacy Officer uitspraken op identieke parameters worden 60s gecached per tenant.
- **Circuit breakers per Officer** — als één Officer crasht, blokkeert de Council in plaats van door te laten. Zie ADR-026 `CircuitBreakerRegistry`.
- **Test-eerst implementatie** — TDD verplicht voor de Coordinator én elke nieuwe Officer (CLAUDE.md kwaliteitsloop).

### AI Act Governance Mapping (ADR-031)

Dit ADR is de kernimplementatie van de AI Act governance contract (ADR-031 §1, §3, §5, §7):

| Vereiste | Bron | Implementatie |
|----------|------|---------------|
| Canonical governance pipeline step 4 | ADR-031 §1 | Council deliberation is the mandatory decision step between policy checks and audit write |
| Autonomy ladder enforcement | ADR-031 §2 | L1-L4 classification via Proposal.data_classification + Officer risk evaluation; L3/L4 actions require HITL |
| Agent contract per execution surface | ADR-031 §3 | Each Officer defines allowed/forbidden actions; Coordinator enforces contract compliance |
| Platform wiring policy | ADR-031 §4 | All Co-Pilot surfaces (HTTP, WS, proactive) route through CopilotService → Council; legacy endpoints sunset |
| Evidence package for compliance | ADR-031 §5 | Every decision produces: traceability (who/when/model), oversight (HITL where required), transparency (explanation_for_user), monitoring (Prometheus metrics + Grafana) |

### Compliance Mapping

| Eis | Bron | Implementatie in deze ADR |
|-----|------|---------------------------|
| Automatische logging van elke AI-beslissing | EU AI Act art. 12 | Council → AuditOfficer → hash chain |
| Logs minimaal 6 maanden bewaren | EU AI Act art. 26(6) | 13 maanden retention (overruled door projecteis) |
| Tamper-evident logs | EU AI Act art. 12, ISO 42001 | SHA-256 hash chain (ADR-019) |
| Instructies voor deployers | EU AI Act art. 13 | Per-tenant config + dashboard (in design doc) |
| Eindgebruiker weet dat hij met AI praat | EU AI Act art. 50 | UI-indicator + tooltip + reasoning transparency |
| Recht op menselijke tussenkomst | GDPR art. 22 | RiskOfficer → OversightGate → HITL UI |
| Recht op uitleg | GDPR art. 13-15 | `explanation_for_user` veld + AuditViewer UI |
| Event log met actor, model, outcome | ISO 42001 A.6.2.8 | Volledig in `CouncilDecision` schema |
| Platform-wide governance contract | ADR-031 | Council is the canonical decision layer for all AI actions across Copilot, CVA, Focus Builder, ALS, Agentic |

### Notes

- Implementatie volgt in **8 weken** zoals beschreven in `docs/copilot-sprint-plan.md`. Council eerst (week 1-3), Co-Pilot consolidatie (week 4), proactieve patronen fase 1 (week 5), frontend (week 6), audit-prep (week 7), hardening (week 8).
- ADR-027 vervangt **niets**; het bouwt voort op ADR-015, ADR-016, ADR-017, ADR-019, ADR-022, ADR-023, ADR-025, ADR-026.
- Bestaande `CopilotOrchestrator` (`src/core/orchestrator/copilot_orchestrator.py`) wordt opgenomen in `CopilotService.execute_after_approval()` voor multi-agent uitvoering ná Council-goedkeuring.
- Fase 2-uitbreidingen (per-tenant Council policy overrides, externe auditor-export, real-time compliance score) staan in het ontwerpdocument onder "Roadmap".

## Implementation Defaults (besloten 2026-05-22)

De volgende technische keuzes zijn aan deze ADR toegevoegd na bevestiging van de architect:

### LLM Output Contract
- **JSON mode verplicht** voor alle LLM-aanroepen die acties produceren.
- DeepSeek + OpenAI: native JSON mode.
- Anthropic: tool-use met JSON schema constraint.
- Pydantic validatie als laatste vangnet; bij parse-fout → 1 retry, daarna VETO.

### Officer Timeouts
| Officer | Timeout | Reden |
|---------|---------|-------|
| ComplianceOfficer | 800ms | LLM-backed classifier |
| PrivacyOfficer | 500ms | Default (snelle PII detectie) |
| SecurityOfficer | 300ms | Lokale checks (allowlist, regex) |
| RiskOfficer | 600ms | Context-zware analyse |
| EthicsOfficer | 500ms | Default (lexicon matching) |
| ResourceOfficer | 200ms | Snelle Redis-counter checks |
| AuditOfficer | 400ms | DB write + hash compute |

Timeout overschrijding → fail-secure VETO interpretation door Coordinator.

### Hash Chain Storage Strategy
**Optie A — backward compatible uitbreiding:**
- Bestaande `governance_audit_log` tabel krijgt nullable extra kolommen voor AI Act-velden.
- Twee nieuwe tabellen: `council_decisions` (Council-specifieke metadata) en `officer_verdicts` (per-Officer details).
- Koppeling via `decision_id` (UUID).
- Geen breaking changes op bestaande audit-queries.

### Officer Versioning
- **Semver per Officer** (bv. `"1.0.0"`, `"1.1.0"` bij verbeteringen, `"2.0.0"` bij breaking changes in verdict-logica).
- Officer.version wordt in élke `officer_verdicts` record opgeslagen.
- Coordinator weigert te starten als een Officer geen versie-string heeft (fail-fast bij dev-fouten).
- Upgrade-strategie: nieuwe Officer-versie draait naast oude voor 1 release-cyclus (shadow mode, niet-blokkerend), daarna full cutover.

## 11. Context Enrichment & Platform Awareness Architecture

### 11.1 Probleemstelling

De huidige `CopilotService.handle_turn()` ontvangt een leeg `context: dict[str, Any]` van de client en geeft dit onveranderd door aan `LLMHandler.get_action()`. De LLM heeft geen kennis van:
- Welke endpoints, agents en tools geregistreerd zijn
- Wat het Digital Twin-profiel van de gebruiker is
- Welke documentatie (ADRs, API specs, runbooks) relevant is
- Wat de platform-health status is

Dit leidt tot hallucinaties (acties die niet bestaan), generieke antwoorden, en een gebrek aan proactieve platform-expertise.

### 11.2 Decision: Multi-Source Context Engine (MSCE)

Voor elke `handle_turn()` voert `CopilotService` een **deterministische, parallelle context-verrijkingsstap** uit vóór de LLM-aanroep. De engine haalt asynchroon op uit vier bronnen en assembleert een gestructureerde `EnrichedContext`.

#### Bron 1: Platform Knowledge Corpus (Document RAG)
- **Scope**: Alle ADRs, frontend feature specs, API endpoint-documentatie, runbooks, domain pack definities, agent profielen
- **Techniek**: Hergebruik van bestaande `HybridSearch` met `MarkdownChunker` + `EmbeddingService`
- **Index lifecycle**: Dramatiq-actor `rebuild_platform_knowledge_index` triggert bij deploy en dagelijks 04:00 UTC
- **Tenant overrides**: Tenant-specifieke feature docs en configuratie overschrijven global docs bij conflict
- **Output**: `list[RetrievedChunk]` met bronvermelding (ADR-nummer, bestandspad, heading)

#### Bron 2: Live Capability Registry (Runtime introspectie)
- **Scope**: Geregistreerde routers, agents, tools, feature flags, health status
- **Techniek**: Directe queries op `RouterRegistry`, `AgentRegistry` (DB-variant), `ToolBroker.allowlist()`, `FeatureFlagService.snapshot()`
- **Cache**: Redis TTL=60s voor registry snapshots; health checks TTL=10s
- **Output**: `CapabilitySnapshot` met actieve endpoints, geregistreerde agent cards, en tenant-scoped tool allowlist

#### Bron 3: Digital Twin & Memory (Personal context)
- **Scope**: `AgentMemoryProfile`, recente `MemoryItem`s (semantisch + episodisch), `SessionMemoryEvent`s
- **Techniek**: `ContextPackerService.build()` voor sessie-boot context; `MemoryRetrievalService.query()` voor relevante memories
- **Consent gate**: Alleen ophalen als `cross_session_memory=true` (ADR-026 §2)
- **Output**: `TwinProfileSnapshot` + `list[RetrievedMemory]`

#### Bron 4: Conversation Memory (Sessie-context)
- **Scope**: Laatste 20 berichten uit `ConversationMemory` (Redis, sliding window)
- **Techniek**: Bestaand; geen wijziging
- **Output**: `list[ChatMessage]`

### 11.3 Context Packing & Token Budget

`ContextPackerService` (bestaand, uit `src/domains/memory`) wordt hergebruikt met een **dynamisch token budget** per LLM provider:

| Provider | Context Window | Budget voor Platform Context |
|----------|---------------|------------------------------|
| DeepSeek | 64K | 12K tokens |
| Kimi 2.6 | 200K | 16K tokens |
| Gemini 1.5 Pro | 1M | 20K tokens |
| Gemini Flash | 1M | 16K tokens |
| Claude 4 | 200K | 16K tokens |

**Truncatie-strategie** (prioriteit, hoog naar laag):
1. Conversation history (altijd behouden, max 2K tokens)
2. Live Capability Registry (compact JSON, max 2K tokens)
3. Digital Twin profile (samenvatting, max 2K tokens)
4. Platform Knowledge chunks (reranked by cross-encoder; truncate lowest score)
5. Session history (reeds in #1)

Bij overschrijding: **knowledge chunks worden eerst getruncate**, nooit twin profile of capability registry.

### 11.4 Injectie in LLM Prompt

`LLMHandler._build_system_prompt()` wordt uitgebreid met drie gestructureerde secties:

```
[PLATFORM KNOWLEDGE]
<retrieved chunks met bronvermelding>

[PLATFORM CAPABILITIES]
<active endpoints, agents, tools als compact JSON>

[USER CONTEXT]
<twin profile summary, recente relevante memories>
```

De bestaande JSON schema instructie blijft onveranderd. De LLM ontvangt dus: schema + capabilities + user context + vraag.

### 11.5 Council Integratie

`DeliberationContext` wordt uitgebreid met:

```python
class DeliberationContext:
    # bestaande velden
    twin_profile: TwinProfileSnapshot | None
    retrieved_knowledge: list[RetrievedChunk]
    capability_map: CapabilitySnapshot
    retrieval_metadata: RetrievalMetadata  # hash van bronnen, voor AuditOfficer
```

**Per Officer impact**:
- **AuditOfficer**: Logt `retrieval_metadata.source_hash` en `retrieval_metadata.tenant_id_scope_check`
- **PrivacyOfficer**: Valideert dat alle `retrieved_knowledge` bronnen `tenant_id` matchen met request tenant; flagt cross-tenant leakage als VETO
- **SecurityOfficer**: Valideert dat `capability_map.tools` subset is van `ToolBroker.allowlist()`; detecteer hallucinaties
- **ComplianceOfficer**: Classificeer op basis van daadwerkelijke action + parameters, niet alleen op action_type string
- **ResourceOfficer**: Reken retrieval latency (target P95 < 200ms) mee in totale turn budget

---

## 12. Platform Capability Registry Integration

### 12.1 Probleem: Vier Conflicterende Registries

De codebase heeft op dit moment **vier onafhankelijke bronnen van waarheid** voor platform capabilities, die niet met elkaar praten:

1. `router_registry.py` — 130 endpoints, statische Python-lijst (1.027 regels; wordt gesplitst naar 3-laags compositie per ADR-033)
2. `src/core/agents/agent_registry.py` — DB-persistent, `str` keys, health tracking
3. `src/core/agents/capabilities/agent_registry.py` — In-memory, `UUID` keys
4. `src/core/services/focus_suggestion_service.py` — Hardcoded `AVAILABLE_AGENTS` (20 nep-agents)
5. `src/core/api/v1/agentic/agent_discovery.py` — Hardcoded fake agents

### 12.2 Decision: Unified Capability Registry (UCR)

We bouwen een **Unified Capability Registry** die de eerste drie registries ontsluit als één querybaar catalogus. De hardcoded lijsten (#4, #5) worden verwijderd en vervangen door queries op de UCR.

**Architectuur**:
```
UnifiedCapabilityRegistry
├── EndpointCatalog      (uit router_registry)
├── AgentCatalog         (uit DB AgentRegistry)
├── ToolCatalog          (uit ToolBroker.allowlist)
└── DomainPackCatalog    (uit DomainPackOrchestrator)
```

**Interface**:
```python
class ICapabilityRegistry(Protocol):
    async def get_endpoints(self, tenant_id: int, tags: set[str] | None = None) -> list[EndpointMeta]
    async def get_agents(self, tenant_id: int, healthy_only: bool = True) -> list[AgentCard]
    async def get_tools(self, tenant_id: int) -> list[ToolMeta]
    async def get_domain_packs(self, tenant_id: int) -> list[DomainPackMeta]
    async def search(self, tenant_id: int, query: str, limit: int = 10) -> list[CapabilityResult]
```

**Caching**:
- Agent health: Redis, TTL 10s
- Endpoint/tool catalog: Redis, TTL 60s
- Zoekindex: In-memory LRU, 1000 entries per tenant, 5m TTL

**Event-gedreven invalidatie**:
- `agent.registered` / `agent.deregistered` → flush agent catalog cache
- `router.updated` → flush endpoint cache
- `toolbroker.allowlist_updated` → flush tool cache
- `domain_pack.deployed` → flush domain pack cache

### 12.3 Agent Card Schema (A2A-geinspireerd)

Voor interoperabiliteit met toekomstige A2A/MCP adoptie:

```python
class AgentCard:
    agent_id: str
    name: str
    description: str
    version: str
    capabilities: list[str]  # capability tags
    input_schema: dict[str, Any]  # JSON schema van verwachte input
    output_schema: dict[str, Any]
    endpoint: str  # URL of internal route
    health_status: "healthy" | "degraded" | "unhealthy"
    tenant_scoped: bool
```

---

## 13. Token Budget & Context Truncation Strategy

### 13.1 Probleem

`LLMHandler` heeft geen token counting. Grote `context` dicts, lange knowledge chunks, of uitgebreide capability catalogs kunnen het context window van de LLM overschrijden. Retry na validatiefout appendt zonder budget check.

### 13.2 Decision: Deterministische Token Budget Enforcement

Vóór elke `complete_json()` call:

1. **Count**: Tiktoken (GPT-4 tokenizer) als universele approximatie, onafhankelijk van provider
2. **Allocate**: System prompt (schema + instructies) krijgt vaste reservering (2K tokens)
3. **Inject**: Context secties in prioriteit (§11.3)
4. **Truncate**: Overschrijding wordt opgevangen door knowledge chunks te verwijderen van laagste rerank-score naar hoogste
5. **Guard**: Als zelfs minimale context (twin + capabilities) het budget overschrijdt, fallback naar "degraded mode" (alleen capabilities, geen twin/knowledge)

**Retry budget**:
- Eerste poging: 100% van beschikbare context
- Retry na validatiefout: max 80% van origineel (om append-overrun te voorkomen)

---

## 14. Multi-Surface Context Contract

### 14.1 Probleem

Elke AI-surface heeft zijn eigen context-mechanisme:
- Copilot: `dict[str, Any]` van HTTP body
- Focus Builder: `SuggestionRequest` met hardcoded agents
- CVA: `vision_context` dict
- Agentic: `TaskData.metadata`

Geen shared Context Engine; inconsistente UX en dubbele implementaties.

### 14.2 Decision: Shared Context Engine Service

`CopilotContextEngine` is **niet copilot-specifiek**. Het wordt `AIContextEngine` in `src/core/ai_context/` en ontsloten voor alle AI surfaces.

**Gebruikers**:
| Surface | Context Engine call | Extra injected context |
|---------|--------------------|------------------------|
| Copilot | `engine.enrich_for_turn(tenant_id, user_id, query)` | conversation history |
| Focus Builder | `engine.enrich_for_suggestion(tenant_id, user_id, prompt)` | active project, selected agents |
| CVA | `engine.enrich_for_vision(tenant_id, user_id, visual_context)` | canvas state, selected nodes |
| Agentic router | `engine.enrich_for_routing(tenant_id, user_id, task)` | supervisor health, queue depth |

**Contract**:
```python
class AIContextEngine:
    async def enrich(self, tenant_id: int, user_id: int, query: str,
                     surface: SurfaceType, extra: dict[str, Any]) -> EnrichedContext
```

Alle surfaces ontvangen dezelfde `EnrichedContext` structuur, maar de `surface` parameter beinvloedt packing prioriteit (bijv. CVA krijgt meer ruimte voor visuele context).

---

## 15. Infrastructure Preconditions & Known Blockers

### 15.1 Blockers die P0 moeten zijn voordat Context Engine productie kan

De volgende gaps uit de architectuur audit (2026-05-27) zijn **geen onderdeel van de Context Engine zelf**, maar blokkeren correcte werking. Ze moeten parallel of vooraf worden opgelost.

| # | Blocker | Ernst | Owner | Impact op Context Engine |
|---|---------|-------|-------|--------------------------|
| B1 | Vector search (`RetrievalEngine`) heeft geen `tenant_id` filter; `global_index` mixed alle tenants | **CRITICAL** | Search | Cross-tenant data leakage in retrieved knowledge chunks |
| B2 | Hybrid search geeft `tenant_id` door aan BM25 maar niet aan vector search; fusion mixt scoped + global | **CRITICAL** | Search | Tenant A ziet documenten van Tenant B in 50% van results |
| B3 | Council factory (`factory.py`) injecteert `_Simple*` mocks voor 6 van 7 Officers | **CRITICAL** | Governance | Council kan retrieved context niet valideren; security checks zijn no-ops |
| B4 | Agent discovery (`agent_discovery.py`) retourneert 10 hardcoded fake agents | **CRITICAL** | Agents | CapabilityRegistry kan geen echte agent metadata ophalen |
| B5 | CopilotService injecteert `twin_service` maar gebruikt het nooit in `handle_turn()` | **HIGH** | Copilot | Twin profile blijft `None` ondanks beschikbaarheid |
| B6 | `LLMHandler` heeft geen token counting of truncation | **HIGH** | Copilot | Context injectie kan context window overrun veroorzaken |
| B7 | BM25 index heeft geen eviction policy; ongebonden geheugengroei per tenant | **HIGH** | Search | OOM bij 1000+ tenants |
| B8 | BM25 Redis cache (3600s) heeft geen invalidatie bij document updates | **HIGH** | Search | Stale search results na edits |
| B9 | `FocusSuggestionService.AVAILABLE_AGENTS` is hardcoded (20 nep-agents) | **HIGH** | Focus Builder | Suggesties verwijzen naar niet-bestaande tools |
| B10 | `OfficerVerdictCache` heeft geen auto-flush op RBAC/policy wijzigingen | **MEDIUM** | Governance | Beleidswijzigingen nemen 60s door; cached VETO/ALLOW kan verkeerd zijn |

### 15.2 Afhankelijkheidsvolgorde

```
Fase 0 (Blockers):    B1, B2 (search tenant isolatie)
                       B3 (Council mocks → real services)
                       B4 (Agent discovery → DB registry)

Fase 1 (Core):        UnifiedCapabilityRegistry
                       AIContextEngine service
                       Platform Knowledge Index pipeline

Fase 2 (Integratie):  Wire AIContextEngine → Copilot
                       Wire AIContextEngine → Focus Builder, CVA, Agentic
                       Twin-Copilot memory sync (ADR-025 Gap #3)

Fase 3 (Hardening):   Token budget enforcement
                       Performance tests (P95 < 300ms retrieval)
                       Chaos tests (search outage, registry outage)
```

---

## 16. Consequences (uitbreiding)

### Positive (toegevoegd)
- **Copilot is platform-bewust**: kan accurate antwoorden geven over capabilities, configuratie, en best practices
- **Consistente context over alle AI surfaces**: gebruiker krijgt dezelfde expertise ongeacht of ze chatten, een flow bouwen, of een agent routeren
- **Citeerbare antwoorden**: elk antwoord gebaseerd op retrieved knowledge bevat bronvermelding (ADR-fragment, endpoint doc)
- **Council kan echt delibereren**: Officers valideren tegen daadwerkelijke capabilities, niet statische regexes
- **LLM-agnostisch**: retrieval en packing zijn pure Python; elke LLM (Kimi, DeepSeek, Gemini) ontvangt dezelfde rijke prompt

### Negative (toegevoegd)
- **Retrieval latency**: 50-200ms extra per turn (parallel, gemeten target P95 < 300ms)
- **Index operationele last**: Platform Knowledge Index moet bij deploy en dagelijks worden gerebuild
- **Geheugendruk**: BM25 + vector indexes per tenant vereisen monitoring en eviction
- **Complexiteit cache invalidatie**: 4 bronnen × 4 invalidatie triggers = 16 event handlers

### Mitigations (toegevoegd)
- **Async parallel retrieval**: `asyncio.gather()` over 4 bronnen; dominant door langzaamste (meestal vector search)
- **Gelaagde cache**: Redis voor registry + BM25; in-memory LRU voor reranked results
- **Degraded mode**: bij retrieval failure → alleen live capabilities (altijd beschikbaar), geen knowledge docs
- **Circuit breakers per bron**: als HybridSearch down is, turn slaagt nog steeds met capabilities + twin

---

## Bekende implementatiebug (GS-1) — vastgesteld 2026-05-28

**Bestand:** `src/core/agents/ethics_agent.py`

**Probleem:** De `_execute_task()` methode van de Ethics Officer heeft GEEN niet-mock
code-pad. Alle uitvoering loopt via:
- `_mock_risk_assessment()` — retourneert willekeurige fake risk scores
- `_mock_ethical_review()` — retourneert nep goedkeuring
- `_mock_compliance_check()` — retourneert altijd `"compliant": true`
- `_mock_general_ethics_check()` — generieke fallback mock

Alle response-objecten bevatten `"mock_analysis": True`. Dit betekent dat elke
Council-deliberatie waarbij de Ethics Officer betrokken is, berust op een nep-analyse.
De daadwerkelijke ethische beoordeling van AI-acties vindt NIET plaats.

**Gevolgen:**
- ADR-027 §7 (Officer deliberatie) is structureel non-operationeel voor de
  ethics-dimensie
- B3 uit §15.1 (Council factory injecteert mocks) wordt verergerd: ook de Ethics
  Officer zelf is een mock, ongeacht factory-injectie
- AI Act Art. 9 (risk management systeem) is niet aantoonbaar
- AI Act Art. 13 (transparantie over AI-risico's) is niet aantoonbaar
- SOC 2 CC7.2 (monitoring van risico's) is niet aantoonbaar

**Vereiste fix (Fase 1 — voor launch):**
```python
# src/core/agents/ethics_agent.py
async def _execute_task(self, task: TaskData) -> dict:
    raise NotImplementedError(
        "EthicsAgent requires a real implementation before production use. "
        "All mock execution paths have been removed. "
        "See docs/frontend/pages/22-platform-p0-blockers-scope.md (GS-1)"
    )
```

**Vereiste fix (Fase 2 — echte implementatie):**
Implementeer ethics assessment via `GuaranteedLLMService` met een AI Act-conform
prompt dat `risk_flags`, `ethics_score: float` en
`recommendation: Literal["approve","review","reject"]` structureel retourneert.

**Prioriteit:** P0 (GS-1) — Council-deliberatie is structureel nep zolang deze fix
niet is doorgevoerd.

Volledig fix-plan: `docs/frontend/pages/22-platform-p0-blockers-scope.md` (GS-1).

---

## Implementatie-bevindingen -- Architectuur Audit 2026-05-31

Bottom-up code trace uitgevoerd op 2026-05-31. Alle bevindingen zijn afkomstig uit directe
bestandslezingen, niet uit documentatie. 9 wiring-fouten gevonden t.o.v. de architectuurbeschrijving
in dit ADR. Gerelateerde sprints: SP-WE-01 t/m SP-WE-08.

### WE-001 [CRITICAL] TenantMiddleware volgorde in L4-flow

**Situatie:** L4-diagram toonde TenantMiddleware als stap *binnen* de endpoint call chain.
**Werkelijkheid:** TenantMiddleware is ASGI-middleware, toegevoegd via `setup_middleware()` in
`middleware_config.py` (regel 103). Draait VOOR endpoint-dispatch via LIFO-stack. Endpoint leest
al-gezet ContextVar via `require_tenant_id()` (`turn_endpoint.py` regel 48).
**Bewijs:** `src/core/api/setup/middleware_config.py:103`, `src/core/copilot/api/turn_endpoint.py:48`
**Impact:** Documentatie misleidend; geen runtime-impact.
**Sprint:** SP-WE-01

### WE-002 [CRITICAL] LLMHandler wordt aangeroepen VOOR ProposalBuilder, niet erna

**Situatie:** ADR beschreef: ProposalBuilder bouwt proposal -> ProposalBuilder roept LLMHandler aan.
**Werkelijkheid:** `CopilotService.handle_turn()` roept eerst `llm_handler.get_action()` aan (regel 171),
daarna `proposal_builder.build()` (regel 181). ProposalBuilder is een pure synchrone wrapper die
nooit LLMHandler aanroept.
**Bewijs:** `src/core/copilot/service.py:171-181`, `src/core/copilot/proposal_builder.py` (geen LLMHandler import)
**Impact:** Architectuurbeschrijving onjuist. Correcte volgorde: LLMHandler -> CopilotAction -> ProposalBuilder.build(action) -> Proposal.
**Sprint:** SP-WE-01

### WE-003 [CRITICAL] ExecutionGuard wordt verkregen NA Council deliberation, niet ervoor

**Situatie:** L4-diagram toonde ExecutionGuard (Redis NX lock) als stap VOOR Council.deliberate().
**Werkelijkheid:** Volgorde in service.py: (1) `council.deliberate(proposal)` regel 192,
(2) `_execute_decision()` regel 199, (3) `start_execution()` binnen _execute_decision.
Council heeft geen idempotency-bescherming.
**Bewijs:** `src/core/copilot/service.py:192-199`
**Impact:** Dubbele request kan twee gelijktijdige Council deliberations triggeren voor dezelfde input.
Idempotency is alleen gewaarborgd voor de executiefase, niet voor de beslissingsfase.
**Sprint:** SP-WE-06 (Council idempotency pre-deliberation lock)

### WE-004 [HIGH] PromptGuard is geen zelfstandige stap -- draait binnen SecurityOfficer

**Situatie:** L4-diagram toonde PromptGuard als aparte stap in de hoofdketen.
**Werkelijkheid:** PromptGuard wordt aangeroepen binnen `SecurityOfficer._actual_deliberate()`
als onderdeel van de 7 parallelle officer-aanroepen. NFD-normalisatie + homoglyph-stripping wordt
toegepast VOOR `prompt_guard.scan()`.
**Bewijs:** `src/core/copilot/council/members/security_officer.py:151-157`
**Impact:** Architectuurdocumentatie incorrect; functioneel gedrag correct.
**Sprint:** SP-WE-01

### WE-005 [HIGH] AuditService vs CouncilAuditWriter -- verkeerde component in L4

**Situatie:** L4-diagram toonde `src/core/audit/audit_service.py` als de audit-component in de copilot-turn flow.
**Werkelijkheid:** Copilot turn gebruikt `CouncilAuditWriter` (`src/core/copilot/council/audit_writer.py`)
met `persist()` en `bind_execution_result()`. `AuditService` behandelt auth/security events (login,
logout, token revocation) -- volledig gescheiden verantwoordelijkheid.
**Bewijs:** `src/core/copilot/dependencies.py:39-47` (importeert CouncilAuditWriter, niet AuditService)
**Impact:** Documentatie incorrect; runtime-gedrag correct.
**Sprint:** SP-WE-01

### WE-006 [HIGH] LLMFallbackChain is niet gewired in de copilot-turn flow

**Situatie:** ADR en L4-diagram toonden LLMFallbackChain als de LLM-component in de copilot-turn flow.
**Werkelijkheid:** `LLMHandler` gebruikt `LLMProviderFactory.get_provider()` voor een enkele concrete
LLMClient-subklasse. LLMFallbackChain (`fallback_chain.py`) is een onafhankelijk hulpmiddel en is
NIET gekoppeld aan de copilot-turn via LLMHandler.
**Bewijs:** `src/core/copilot/dependencies.py:34`, `src/core/copilot/llm_handler.py:71`
**Impact:** CircuitBreakerRegistry niet actief in copilot-turn. Single provider failure = directe fout
zonder automatische failover.
**Sprint:** SP-WE-07 (LLMFallbackChain wiring)

### WE-007 [HIGH] EthicsOfficer heeft can_veto=False en is fail-open

**Situatie:** ADR §5.2.5 impliceert dat EthicsOfficer BLOCKED kan veroorzaken.
**Werkelijkheid:** `can_veto=False` (`ethics_officer.py` regel 69). Op error: retourneert APPROVE
(fail-open). Als het toch VETO zou emitteren degradeert `_aggregate()` dit naar DEFERRED.
**Bewijs:** `src/core/copilot/council/members/ethics_officer.py:69`,
`src/core/copilot/council/coordinator.py:283-296`
**Impact:** Ethische overtredingen kunnen niet door EthicsOfficer geblokkeerd worden.
ComplianceOfficer en SecurityOfficer (beide can_veto=True) zijn de enige blokkerende Officers.
**Besluit vereist:** Bewuste MVP-keuze documenteren OF can_veto=True + fail-secure implementeren.
**Sprint:** SP-WE-05

### WE-008 [HIGH] AuditOfficer is geen onderdeel van de parallelle gather-batch

**Situatie:** ADR en diagram toonden AuditOfficer als 8e Officer in de parallelle gather-batch.
**Werkelijkheid:** AuditOfficer is NIET in `_voting_officers` tuple (7 items: Compliance, Privacy,
Security, Risk, Ethics, Resource, Sanity). `AuditOfficer.deliberate()` retourneert hardcoded
APPROVE/AUDIT_ACK. Het echte werk zit in `finalize_and_persist()` -- aangeroepen NA aggregatie in `_finalize()`.
**Bewijs:** `coordinator.py:87-93`, `audit_officer.py:79-113`
**Impact:** Architectuurbeschrijving incorrect. AuditOfficer is een post-aggregatie serializer, geen stemmer.
**Sprint:** SP-WE-01

### WE-009 [HIGH] AgentCouncil is geen singleton -- nieuwe instantie per request

**Situatie:** ADR en codebase-documentatie suggereerden dat AgentCouncil een singleton is.
**Werkelijkheid:** `build_council(db)` in factory.py maakt per FastAPI-request een volledig nieuwe
AgentCouncil-instantie aan (incl. alle 8 officers, ShadowCEO, SignalBus, PracticalTwinService,
RedisRateLimiter, NotificationBudgetTracker, UserBehaviorObserver). Geen caching op factory-niveau.
**Bewijs:** `factory.py:215-302` (build_council() zonder caching)
**Impact:** Aanzienlijke object-instantiatie overhead per request. ResourceOfficer's InMemoryRateLimiter
wordt elke keer gereset -- rate limiting is dus niet persistent over requests.
**Sprint:** SP-WE-08 (Council singleton/caching architectuur)

### Correcte L4-volgorde (na audit)

De werkelijke call-volgorde in `CopilotService.handle_turn()`:

```text
ASGI Stack (voor dispatch -- LIFO volgorde):
  ProbeBypassMiddleware -> SecurityMiddleware -> SecurityHeadersMiddleware
  -> TenantMiddleware (JWT verify + set ContextVar) -> TenantQuotaMiddleware

HTTP Layer (per request, via FastAPI DI):
  copilot_turn_limit (rate limiter, 30/60s per tenant_id)
  -> get_current_user DI (2e JWT-verificatie + DB user lookup)
  -> get_copilot_service DI (build_council + alle providers PER request -- geen singleton)
  -> get_db DI (SET LOCAL app.current_tenant voor PostgreSQL RLS)

CopilotService.handle_turn():
  1. _augment_context() -> SubagentLoader.list_available_agents() + lege tools []
     (twin_service altijd None in productie -- WE-016)
  2. llm_handler.get_action() -> LLMProviderFactory.get_provider().complete_json()
     (NIET via LLMFallbackChain -- WE-006)
     -> CopilotAction
  3. proposal_builder.build(action) -> Proposal [synchroon, roept LLMHandler NIET aan]
  4. council.deliberate(proposal):
     a. _gather_verdicts(): asyncio.gather(7 voting officers) [parallel, timeout per officer]
        - ComplianceOfficer (can_veto=True, Redis TTL=60s cache)
        - PrivacyOfficer (can_veto=True, consent check NOOIT actief: twin_profile=None -- WE-017)
        - SecurityOfficer (can_veto=True, roept PromptGuard intern aan -- WE-004)
        - RiskOfficer (can_veto=True, ShadowCEO assess)
        - EthicsOfficer (can_veto=False, fail-open op error -- WE-007)
        - ResourceOfficer (can_veto=False, InMemoryRateLimiter reset per request -- WE-009)
        - SanityOfficer (can_veto=True, fail-secure: error->VETO)
        AuditOfficer staat NIET in deze batch -- WE-008
     b. _aggregate(): VETO(can_veto)->BLOCKED, VETO(no can_veto)->DEFERRED,
        REQUIRE_HITL->HITL_REQUIRED, MODIFY->MODIFIED, else APPROVED
     c. _finalize(): AuditOfficer.finalize_and_persist() [NA aggregatie]
  5. _route_verdict():
     - HITL_REQUIRED: hitl_repo.create_hitl_request()
     - BLOCKED: _blocked_response(uuid4())
     - APPROVED + tool_broker + action_type: _execute_decision()
       -> ExecutionGuard.start_execution() [Redis SET NX -- NA council, niet ervoor -- WE-003]
       -> tool_broker.execute_tool() [HITL gate leest in-memory dict -- WE-018]
       -> ExecutionGuard.finish_execution(SUCCESS|FAILED) [in finally]
  6. CouncilAuditWriter.bind_execution_result() [best_effort] (NIET AuditService -- WE-005)
```

---

## Implementatie-bevindingen -- L3 Wiring Audit 2026-06-01

### CG-001 [CRITICAL] ComplianceOfficer krijgt bare object() in plaats van ComplianceGuardian

**Situatie:** ADR-027 §5.2.1 beschrijft ComplianceOfficer als wrapper om een echte `ComplianceGuardian`.
**Werkelijkheid:** `factory.py` regel 237 injecteert `compliance_guardian=object()` -- een kaal
Python-object zonder enige methode. `ComplianceOfficer.__init__` verwacht een `ComplianceGuardian`
instantie met echte methoden. Elke aanroep naar `self._guardian.any_method()` gooit een
`AttributeError` bij runtime, waardoor compliance-checks stil falen of de deliberatie crasht.
**Bewijs:** `src/core/copilot/council/factory.py:237`: `compliance_guardian=object()`.
**Impact:** Elke copilot turn die ComplianceOfficer deliberatie triggert riskeert een onafgehandelde
`AttributeError`. Compliance verdicts kunnen incorrect zijn of de volledige deliberatie kan falen,
waardoor alle copilot requests geblokkeerd worden. EU AI Act compliance is niet aantoonbaar.
**Fix:** Vervang `compliance_guardian=object()` door een echte `ComplianceGuardian` instantie
of een correcte `NullComplianceGuardian` stub die alle methoden die de officer aanroept implementeert.
**Sprint:** SP-WE-10 (P0, te plannen)

### CG-004 [HIGH] hitl_repo altijd None -- HITL_REQUIRED verdict wordt stil genegeerd

**Situatie:** ADR-027 beschrijft dat HITL_REQUIRED verdicts een human review ticket aanmaken.
**Werkelijkheid:** `hitl_repo` parameter wordt NOOIT doorgegeven vanuit `_build_copilot_service()`
in `dependencies.py` -- altijd `None`. De HITL_REQUIRED branch in `service.py` regel 471 bevat
de guard `if self._hitl_repo:` die altijd `False` is. Geen enkel human review ticket wordt ooit
aangemaakt. Het `IHITLRepository` Protocol bestaat maar heeft geen concrete adapter in de DI-keten.
**Bewijs:** `src/core/copilot/dependencies.py` (geen `hitl_repo=` parameter bij CopilotService
constructie), `src/core/copilot/service.py:471` (`if self._hitl_repo:` guard).
**Impact:** High-risk copilot acties die naar een menselijke operator geescaleerd zouden moeten worden
(HITL_REQUIRED Council verdict) worden stil genegeerd. De ADR-015 HITL-gate is non-functioneel in productie.
**Fix:** Instantieer een concrete `HITLRepository` (gebaseerd op `HITLStore` uit
`src/core/tool_broker/hitl_store.py`) en injecteer hem als `hitl_repo` in `CopilotService`
via `_build_copilot_service` in `src/core/copilot/dependencies.py`.
**Sprint:** SP-WE-15 (P0, te plannen -- raakt ook ADR-015)

### CG-003 [HIGH] NotificationDispatcher nooit geinstantieerd bij startup

**Situatie:** ADR-027 Sprint 5 beschrijft een volledige notification pipeline.
**Werkelijkheid:** `NotificationDispatcher` wordt nergens geinstantieerd bij app-startup.
`app.state.notification_dispatcher` wordt nooit gezet in `app_lifespan.py`.
`DigestGenerator` heeft nul callsites in productiecode. Alle proactieve monitors en compliance
monitors skippen notification dispatch stil, waardoor de volledige Sprint 5 notification pipeline inert is.
**Bewijs:** `src/core/app_lifespan.py` (geen `notification_dispatcher` instantiatie),
grep op `DigestGenerator(` in `src/`: nul resultaten.
**Impact:** AgentHealth, WorkflowLatency, QueueDepth, TokenSpike, CircuitBreaker,
ConsentExpiry, AuditAnomaly, DSARExport, PolicyChange en SensitiveWorkflow signalen worden
gegenereerd maar nooit afgeleverd. Budget alerts, CRITICAL popups en digest emails worden nooit verstuurd.
**Fix:** Instantieer `NotificationDispatcher` met `WSPusher`, `DigestQueue`, `budget_tracker`
en `preferences_repo` in `app_lifespan.py` en wijs toe aan `app.state.notification_dispatcher`.
**Sprint:** SP-WE-16 (P1, te plannen)

---

## Changelog

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-05-23 | Architecture Team | Initial decision — Council + Copilot consolidation |
| 1.1 | 2026-05-24 | Engineering | Sprint 3 hardening + Sprint 4 dag 1 (CopilotService, LLMHandler, ProposalBuilder) |
| 1.2 | 2026-05-26 | Governance program | ADR-031 completion; all P0 gaps resolved; program GO |
| 1.3 | 2026-05-27 | Architecture Team | §11-15 toegevoegd: Context Enrichment Architecture, Unified Capability Registry, Token Budget, Multi-Surface Contract, Infrastructure Preconditions & Known Blockers |
| **1.4** | **2026-05-28** | **Ground-truth scan** | **GS-1 bug gedocumenteerd: ethics_agent.py uitsluitend mock execution paths; Council-deliberatie structureel nep; fix-patroon vastgelegd** |
| **1.5** | **2026-05-31** | **Architectuur Audit** | **9 wiring-fouten gedocumenteerd (WE-001 t/m WE-009): correcte L4-volgorde vastgelegd, EthicsOfficer can_veto=False gedocumenteerd, AgentCouncil per-request instantiatie gedocumenteerd, LLMFallbackChain niet gewired, ExecutionGuard na Council** |
| **1.6** | **2026-06-01** | **SP-WE-05** | **EthicsOfficer can_veto=False bevestigd als expliciete MVP-beslissing (WE-007). Lexicon-based checks hebben hoog false-positive risico voor zakelijke content. Fail-open op error (APPROVE) is bewust. LLM-based ethics enforcement gepland voor post-MVP. ComplianceOfficer + SecurityOfficer (can_veto=True) dekken BLOCKED-verdicts.** |

## References

- `docs/copilot-feature-context.md` — audit huidige staat (2026-05-22)
- `docs/copilot-architecture.md` — uitgewerkt ontwerpdocument
- `docs/copilot-sprint-plan.md` — 8-weken implementatieplan
- **Gap Analysis Report 2026-05-27** — `docs/reports/COPILOT_CONTEXT_ENGINE_GAP_ANALYSIS_2026-05-27.md` — 34 gaps, 6 CRITICAL
- ADR-005 (Tenant RLS), ADR-014 (Observability), ADR-015 (ToolBroker), ADR-016 (Shadow CEO), ADR-017 (Gatekeeper), ADR-019 (Audit), ADR-022 (LearningMixin), ADR-023 (AgentRouter), **ADR-025 (Digital Twin)**, **ADR-026 (Twin Hardening)**
- EU AI Act art. 12, 13, 26(6), 50 — Regulation (EU) 2024/1689
- GDPR art. 13-15, 22 — Regulation (EU) 2016/679
- ISO/IEC 42001:2023 A.6.2.8
