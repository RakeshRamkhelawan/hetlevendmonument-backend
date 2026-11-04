# PRD: Paperclip AI Symbiotic Integration

**Version:** 1.2
**Datum:** 11 maart 2026 (v1.2: critical corrections based on repository verification)
**Auteur:** SanskritiSetu Engineering
**Status:** Draft
**Prioriteit:** P0 — Strategic Platform Evolution

---

## Inhoudsopgave

1. [Product Vision](#1-product-vision)
2. [Probleemstelling](#2-probleemstelling)
3. [Strategische Rationale](#3-strategische-rationale)
4. [Feature Specificaties](#4-feature-specificaties)
5. [Architectuur Design](#5-architectuur-design)
6. [Data Models & Migraties](#6-data-models--migraties)
7. [API Design](#7-api-design)
8. [Frontend Integratie](#8-frontend-integratie)
9. [Migratie & Backward Compatibility](#9-migratie--backward-compatibility)
10. [Rollout Plan](#10-rollout-plan)
11. [Testing Strategie](#11-testing-strategie)
12. [Security & Compliance](#12-security--compliance)
13. [Success Metrics & KPIs](#13-success-metrics--kpis)
14. [Risico's & Mitigaties](#14-risicos--mitigaties)
15. [Appendix](#15-appendix)

---

## 1. Product Vision

### 1.1 One-Liner

SanskritiSetu evolueert van een **agent orchestration platform** naar een **company orchestration platform** door Paperclip AI's "company-as-code" paradigma symbiotisch te integreren met de bestaande 161 agents, 80+ Domain Packs, OODA workflow engine, en enterprise governance stack.

### 1.2 Visie Statement

> Na integratie kan elke tenant een **virtueel bedrijf** modelleren — compleet met organigram, afdelingen, doelhiërarchie, en budgetten — waarbij SanskritiSetu's Domain Packs automatisch worden geactiveerd op basis van de bedrijfsstructuur, externe agents via een open heartbeat protocol naadloos meedraaien, en elke taak altijd traceert naar het bedrijfsdoel ("het waarom").

### 1.3 Wat verandert er NIET

- De bestaande 161 interne agents blijven ongewijzigd functioneren
- Domain Packs, Multi-Pack Assembly, en Pack Intelligence blijven intact
- OODA workflow engine, policy engine, en tenant isolation blijven de kern
- Alle bestaande API endpoints blijven backward-compatible
- De huidige frontend componenten blijven werken

### 1.4 Wat komt erbij

| Paperclip Concept | SanskritiSetu Integratie |
|---|---|
| Company Model | Nieuwe `Company` laag bovenop bestaande `Tenant` |
| Org Chart | Hierarchische departement-structuur gekoppeld aan Domain Packs |
| Goal Ancestry | Doelhiërarchie (missie → project → taak) in OODA context |
| Heartbeat Protocol | Open agent-protocol voor externe agents naast interne agents |
| Company Templates | Exporteerbare bedrijfsstructuren die packs + config bundelen |
| Board Governance | Niet-technische governance-metafoor bovenop PolicyEngine |

### 1.5 De Drie Gouden Regels (Architecturele Invarianten)

Elk pad in het systeem — company creation, department routing, pack activation, procedure execution, external-agent dispatch, approval flows, en dashboards — MOET dezelfde vraag beantwoorden: **"Voor welk bedrijfsdoel gebeurt deze actie nu?"**

Dit wordt afgedwongen door drie architecturele regels die als harde invarianten gelden:

| # | Regel | Enforcement | Faailt wanneer |
|---|---|---|---|
| **R1** | **Geen task execution zonder contextobject** met minimaal `company_id`, `department_id`, en `goal_chain` | `AgentExecutionContext` is verplicht parameter in `process_task()` en `ExternalAgentBridge.dispatch()`. Validatie faalt als required fields ontbreken. | Een agent of externe agent een taak ontvangt zonder volledige context. Systeem blokkeert execution en logt `CONTEXT_INCOMPLETE` event. |
| **R2** | **Geen pack-activatie zonder verklaarbare matchreden en confidence score** | `PackActivationResult` bevat altijd `match_reason: str`, `confidence: float`, `input_signals: list`, en `audit_log_id: UUID`. Activatie zonder deze velden is een schema-validatiefout. | Een pack wordt geactiveerd zonder dat de tenant of audit trail kan zien *waarom*. |
| **R3** | **Geen governance-beslissing zonder zichtbaar verband met doel, risico, en budgetcontext** | `BoardDecision.action_context` bevat verplicht `goal_id`, `risk_level`, en `budget_impact`. `BoardService.submit()` valideert completeness. | Een approval wordt gevraagd zonder dat de board member weet welk doel, risico, en budget het betreft. |

> **Implicatie:** Tenants die de Company Layer nog niet gebruiken (§9.2) krijgen een automatisch gegenereerde `default_context` met `company_id=null` en `goal_chain=[]`. De regels gelden altijd — het systeem degradeert graceful maar logt ontbrekende context als `CONTEXT_DEGRADED` metric.

---

## 2. Probleemstelling

### 2.1 Huidige Beperkingen

**P1: Geen bedrijfsmodel als first-class concept**
Tenants zijn technische isolatie-eenheden. Er is geen concept van "dit bedrijf is een retail-MKB met 3 afdelingen". Domain Packs worden handmatig geselecteerd, niet automatisch geactiveerd op basis van bedrijfstype.

**P2: Agents zijn een gesloten ecosysteem**
Alle 161 agents zijn intern gedefinieerd via `EnhancedBaseAgent`. Klanten met eigen scripts, Claude Code sessies, of externe tools kunnen deze niet als "agents" laten meedraaien in workflows.

**P3: Taken missen context over "het waarom"**
Een `ProcedureExecution` weet welke stappen het uitvoert, maar niet welk bedrijfsdoel het dient. Multi-Pack Assembly combineert packs, maar zonder doelhiërarchie die de volgorde en prioriteit stuurt.

**P4: Governance spreekt technische taal**
De `PolicyEngine` werkt met `action_patterns`, `risk_levels`, en `RBAC roles`. Een MKB-eigenaar begrijpt "de board moet dit goedkeuren" beter dan "CRITICAL risk_level vereist approval gate".

**P5: Onboarding is complex**
De huidige setup vereist Docker + PostgreSQL + Redis + RabbitMQ. Voor de ZZP/MKB-doelgroep is dit een te hoge drempel.

### 2.2 Impact

| Probleem | Impact | Betreft |
|---|---|---|
| P1 | Klanten moeten handmatig packs kiezen i.p.v. automatisch matching op bedrijfstype | Pack adoption rate |
| P2 | Verlies van klanten die eigen agent-tooling willen integreren | Platform lock-in perceptie |
| P3 | Agents optimaliseren lokaal (taak) i.p.v. globaal (bedrijfsdoel) | Workflow kwaliteit |
| P4 | Enterprise governance features worden niet gebruikt door MKB | Feature adoption |
| P5 | MKB/ZZP-doelgroep haakt af bij setup | Addressable market |

---

## 3. Strategische Rationale

### 3.1 Waarom Paperclip, niet zelf bouwen?

Paperclip AI (MIT-licentie, 14.6k stars, maart 2026) heeft bewezen concepten die direct aansluiten:

| Paperclip Concept | Bewezen door | Onze Equivalent (nu) | Gap |
|---|---|---|---|
| Company-as-code | 14.6k GitHub stars | `Tenant` model | Geen bedrijfsstructuur |
| Heartbeat protocol | Runtime-agnostisch, productie-bewezen | `EnhancedBaseAgent` | Alleen interne agents |
| Goal ancestry | Elke taak traced naar missie | `ProcedureExecution` | Geen doel-keten |
| Board governance | Niet-technische goedkeuring | `PolicyEngine` | Technische interface |
| Company templates | Export/import met secret-scrubbing | `GlobalPack` repository | Pack-niveau, niet bedrijf-niveau |

### 3.2 Symbiotisch, niet vervangend

Dit is **geen migratie** naar Paperclip. Dit is het adopteren van Paperclip's abstractielaag als **nieuwe laag bovenop** de bestaande stack:

```
┌─────────────────────────────────────────────────┐
│            COMPANY LAYER (nieuw)                 │
│  Company Model · Org Chart · Goal Ancestry       │
│  Board Governance · Company Templates            │
│  Heartbeat Protocol (externe agents)             │
├─────────────────────────────────────────────────┤
│         BESTAANDE SANSKRITISETU STACK             │
│  161 Agents · 80+ Domain Packs · OODA Engine    │
│  PolicyEngine · Multi-Pack Assembly · Hybrid Search│
│  Knowledge Management · Cost/Budget Tracking     │
│  Pack Intelligence · Feedback Loop · CVA         │
├─────────────────────────────────────────────────┤
│            INFRASTRUCTURE                        │
│  PostgreSQL · Redis · RabbitMQ · Docker           │
│  Multi-Tenant Isolation · Audit Logging          │
└─────────────────────────────────────────────────┘
```

### 3.3 Marktpositionering na integratie

| Segment | Vóór integratie | Ná integratie |
|---|---|---|
| Enterprise | Agent orchestration platform | **Company orchestration platform** |
| MKB | Domain Pack marketplace | **"Start je AI-bedrijf in 1 klik"** |
| ZZP | Freelancer productivity tools | **"Je eigen AI-medewerker"** |
| Developer | Gesloten agent platform | **Open ecosystem (BYO agents)** |

---

## 4. Feature Specificaties

### Feature 1: Company Model

#### 4.1.1 Beschrijving

Elke tenant kan één of meerdere **Companies** aanmaken. Een Company is een virtueel bedrijfsmodel dat de structuur, doelen, en agentconfiguratie vastlegt. Het koppelt automatisch aan de juiste Domain Packs op basis van bedrijfstype.

#### 4.1.2 User Stories

| ID | Story | Prioriteit |
|---|---|---|
| US-1.1 | Als tenant admin wil ik een company aanmaken met naam, type (MKB/Enterprise/ZZP), en sector zodat het platform automatisch relevante packs activeert | P0 |
| US-1.2 | Als tenant admin wil ik een organigram definiëren met afdelingen zodat agents en packs per afdeling worden georganiseerd | P0 |
| US-1.3 | Als tenant admin wil ik een company template kiezen (bijv. "Retail MKB", "Tech Startup") zodat ik niet alles handmatig hoef in te richten | P1 |
| US-1.4 | Als systeem wil ik automatisch Domain Packs activeren wanneer een afdeling wordt toegevoegd (bijv. HR-afdeling → `hr.*` packs) | P0 |
| US-1.5 | Als tenant admin wil ik de company configuratie exporteren zodat ik deze kan delen of dupliceren | P2 |

#### 4.1.3 Mapping naar bestaande code

| Nieuw Concept | Koppelt aan | Relatie |
|---|---|---|
| `Company` | `Tenant` (multi-tenant) | 1 tenant → N companies |
| `Department` | `DomainPack.department` field | Department activeert matching packs |
| `CompanyType` | Pack categorieën (enterprise/mkb/zzp) | Filtert beschikbare packs |
| `CompanyTemplate` | `GlobalPack` repository | Bundelt meerdere packs + config |

#### 4.1.4 Automatische Pack Activatie — Beslismatrix

Pack activatie MOET deterministisch, uitlegbaar en auditbaar zijn (Gouden Regel R2). Hieronder de volledige beslislogica:

**Stap 1: Input Signalen verzamelen**

| Signaal | Bron | Gewicht | Voorbeeld |
|---|---|---|---|
| `department_name` | Org chart | 0.40 | "Sales" |
| `company_type` | Company model | 0.20 | "mkb" |
| `sector` | Company model | 0.20 | "retail" |
| `explicit_pack_ids` | Template of user selectie | 0.20 | `["mkb.digital_storefront"]` |

**Stap 2: Score Model**

```python
class PackActivationScorer:
    """Deterministisch scoremodel voor pack matching"""

    def score(self, pack: DomainPack, signals: ActivationSignals) -> PackScore:
        score = 0.0
        reasons = []

        # 1. Department name match (exact of fuzzy)
        dept_match = self._match_department(pack.department, signals.department_name)
        if dept_match.exact:
            score += 0.40
            reasons.append(f"Department exact match: {pack.department}")
        elif dept_match.fuzzy_score > 0.7:
            score += 0.40 * dept_match.fuzzy_score
            reasons.append(f"Department fuzzy match: {dept_match.fuzzy_score:.0%}")

        # 2. Company type match
        if pack.pack_id.startswith(signals.company_type + "."):
            score += 0.20
            reasons.append(f"Pack prefix matches company type: {signals.company_type}")

        # 3. Sector match via intent_tags
        sector_overlap = set(pack.intent_tags) & set(signals.sector_tags)
        if sector_overlap:
            score += 0.20 * (len(sector_overlap) / max(len(pack.intent_tags), 1))
            reasons.append(f"Sector tag overlap: {sector_overlap}")

        # 4. Explicit selection
        if pack.pack_id in signals.explicit_pack_ids:
            score += 0.20
            reasons.append("Explicitly selected by user/template")

        return PackScore(pack_id=pack.pack_id, score=score, reasons=reasons)
```

**Stap 3: Confidence Thresholds & Beslisregels**

| Confidence | Score Range | Actie | User Override |
|---|---|---|---|
| **Exact** | >= 0.90 | Automatisch activeren | Kan deactiveren |
| **High** | 0.70 - 0.89 | Automatisch activeren + suggestie tonen | Kan deactiveren |
| **Medium** | 0.50 - 0.69 | **Suggestie** — user moet bevestigen | Kan activeren of negeren |
| **Low** | 0.30 - 0.49 | Tonen als "misschien relevant" | Kan handmatig activeren |
| **None** | < 0.30 | Niet tonen | Kan handmatig zoeken en toevoegen |

**Stap 4: Conflict Resolution**

| Conflict | Regel |
|---|---|
| Meerdere packs met dezelfde capability | Hoogste score wint; bij gelijke score: platform template pack eerst |
| Pack vereist capability die conflicteert | Beide tonen met waarschuwing, user kiest |
| Budget overschrijding door te veel packs | Toon budget impact per pack, user kiest welke te activeren |

**Stap 5: Audit Trail (Gouden Regel R2)**

Elke pack activatie genereert een `PackActivationResult`:

```python
class PackActivationResult(BaseModel):
    pack_id: str
    pack_name: str
    confidence: float                    # 0.0 - 1.0
    match_reason: str                    # Menselijk leesbare uitleg
    input_signals: List[str]             # Welke signalen zijn gebruikt
    score_breakdown: Dict[str, float]    # Per-signaal score
    audit_log_id: UUID                   # Referentie naar audit log entry
    activated_automatically: bool        # True als confidence >= 0.70
    user_confirmed: Optional[bool] = None  # None als auto, True/False als user keuze
```

**Voorbeeld Flow:**

```
Company aangemaakt: type="mkb", sector="retail"
Afdeling toegevoegd: "Sales"
    ↓
Scorer evalueert 80+ packs tegen signalen:
  mkb.digital_storefront  → score=0.80 (dept=0.40 + type=0.20 + sector=0.20) → AUTO
  mkb.customer_pulse      → score=0.75 (dept=0.35 + type=0.20 + sector=0.20) → AUTO
  sales.lead_enrichment   → score=0.60 (dept=0.40 + sector=0.20)             → SUGGESTIE
  enterprise.sales_analytics → score=0.25 (dept=0.25)                        → niet getoond
    ↓
Audit trail: 3 packs geëvalueerd voor "Sales", 2 auto-geactiveerd, 1 gesuggereerd
Tenant ziet: "2 packs geactiveerd, 1 suggestie wacht op bevestiging"
```

---

### Feature 2: Goal Ancestry (Doelhiërarchie)

#### 4.2.1 Beschrijving

Elk doel in het systeem is onderdeel van een hiërarchie: **Company Mission → Strategic Goal → Project Goal → Task**. Agents ontvangen bij elke taak de volledige doelketen zodat ze beslissingen kunnen nemen in de juiste context.

#### 4.2.2 User Stories

| ID | Story | Prioriteit |
|---|---|---|
| US-2.1 | Als tenant admin wil ik een company mission definiëren zodat alle workflows traceren naar dit doel | P0 |
| US-2.2 | Als tenant admin wil ik strategic goals aanmaken onder de missie zodat afdelingen weten wat hun prioriteiten zijn | P0 |
| US-2.3 | Als systeem wil ik bij elke `ProcedureExecution` de volledige goal chain meegeven zodat agents context hebben | P0 |
| US-2.4 | Als agent wil ik de goal ancestry zien in mijn `TaskData` zodat ik betere beslissingen kan nemen in de OODA Orient-fase | P1 |
| US-2.5 | Als gebruiker wil ik in Mission Control de goal tree visualiseren met voortgang per goal | P1 |

#### 4.2.3 Integratie met OODA Loop

De goal ancestry verrijkt elke fase van de OODA-loop:

```
OBSERVE: Verzamel data relevant voor het DOEL (niet alleen de taak)
         goal_context: {
           mission: "Marktleider worden in duurzame retail",
           strategic_goal: "Operationele kosten met 20% verlagen",
           project_goal: "Supply chain optimalisatie Q2",
           current_task: "Analyseer leverancierscondities"
         }

ORIENT:  Analyseer met bedrijfsdoel als lens
         → Agent weegt opties af tegen strategic_goal
         → Prioriteert acties die supply chain cost reduction dienen

DECIDE:  Beslissing traceert naar goal
         → Decision rationale bevat goal_alignment_score
         → Conflicterende doelen worden geëscaleerd

ACT:     Uitvoering met audit trail naar goal
         → ProcedureExecution.goal_chain = [mission_id, strategic_id, project_id]
         → ROI tracking per goal level
```

#### 4.2.4 Goal Alignment als Runtime Validatie (niet alleen audit)

Goal alignment is een **first-class runtime concept** — het wordt gevalideerd **vóór** execute, niet alleen als audit achteraf. Dit is het mechanisme waarmee Gouden Regel R1 operationeel wordt.

```python
class GoalAlignmentValidator:
    """
    Valideert dat een voorgestelde actie past bij de actieve goal chain.
    Wordt aangeroepen door DomainPackOrchestrator VOORDAT een step wordt uitgevoerd.
    """

    async def validate(
        self,
        proposed_action: str,
        context: AgentExecutionContext,
    ) -> GoalAlignmentResult:
        """
        Returns:
          - ALIGNED: actie past bij goal chain → proceed
          - DRIFT_WARNING: actie is tangentieel → proceed + log warning
          - MISALIGNED: actie conflicteert met goal → block + escalate
        """
        if not context.goal_chain.is_complete():
            # Degraded mode: geen goal chain beschikbaar
            return GoalAlignmentResult(
                status="DRIFT_WARNING",
                reason="Goal chain incomplete — degraded mode",
                goal_alignment_score=0.0,
            )

        # Score berekenen via keyword overlap + semantic similarity
        alignment_score = await self._compute_alignment(
            action=proposed_action,
            goal_chain=context.goal_chain,
        )

        if alignment_score >= 0.6:
            return GoalAlignmentResult(status="ALIGNED", score=alignment_score)
        elif alignment_score >= 0.3:
            return GoalAlignmentResult(status="DRIFT_WARNING", score=alignment_score)
        else:
            return GoalAlignmentResult(status="MISALIGNED", score=alignment_score)
```

**Integratie in execution pipeline:**

```
DomainPackOrchestrator._run_single_step(step, context)
    │
    ├─ 1. GoalAlignmentValidator.validate(step.action, context)
    │     → ALIGNED:       proceed to step 2
    │     → DRIFT_WARNING: log metric, proceed to step 2
    │     → MISALIGNED:    escalate to BoardService, BLOCK execution
    │
    ├─ 2. PolicyEngine.validate_action(step.action, context.policy_scope)
    │     → (bestaande governance check)
    │
    └─ 3. Agent.process_task(task) of ExternalAgentBridge.dispatch(task)
          → Uitvoering met volledige context
```

**Meetbare uitkomst:** Elke execution heeft een `goal_alignment_score` (0.0-1.0) in de audit trail. Dit voedt de KPI "% beslissingen met traceerbare goal-alignment" (§13.4).

#### 4.2.5 Mapping naar bestaande code

| Nieuw Concept | Koppelt aan | Hoe |
|---|---|---|
| `Goal` model | `ProcedureExecution` | `execution.goal_id` → traces naar goal chain |
| Goal context | `EnhancedBaseAgent.process_task()` | `TaskData` krijgt `goal_ancestry` field via `AgentExecutionContext` |
| Goal alignment validator | `DomainPackOrchestrator._run_single_step()` | Pre-execution validatie — blokkeert bij MISALIGNED |
| Goal alignment | `PolicyEngine.validate_action()` | Actions worden ook getoetst aan goal relevance |
| Goal visualization | Mission Control dashboard | Goal tree component met progress bars |
| Goal-based ROI | `ROIService` | ROI aggregatie per goal level |

---

### Feature 3: Heartbeat Protocol (Open Agent Ecosystem)

#### 4.3.1 Beschrijving

Een open protocol waarmee **externe agents** (Claude Code sessies, Python scripts, shell commands, webhooks, n8n flows) als volwaardige deelnemers in SanskritiSetu workflows meedraaien. Elke runtime die een heartbeat kan sturen, is een agent.

#### 4.3.2 User Stories

| ID | Story | Prioriteit |
|---|---|---|
| US-3.1 | Als developer wil ik mijn Python script registreren als externe agent zodat het taken kan ontvangen vanuit Domain Packs | P0 |
| US-3.2 | Als externe agent wil ik heartbeats sturen zodat het platform weet dat ik actief ben | P0 |
| US-3.3 | Als systeem wil ik externe agents dezelfde governance (PolicyEngine) toepassen als interne agents | P0 |
| US-3.4 | Als tenant admin wil ik externe agents toewijzen aan afdelingen in het organigram | P1 |
| US-3.5 | Als systeem wil ik failover uitvoeren wanneer een externe agent 3 heartbeats mist | P1 |
| US-3.6 | Als developer wil ik een SDK/CLI waarmee ik in 3 regels code een agent registreer | P1 |
| US-3.7 | Als systeem wil ik externe agents naadloos combineren met interne agents in Multi-Pack Assembly | P0 |

#### 4.3.3 Protocol Specificatie

```
REGISTRATIE
POST /api/v1/agents/external/register
{
  "name": "my-python-analyzer",
  "runtime": "python",           // python | node | shell | webhook | claude-code
  "capabilities": ["analyze", "report"],
  "heartbeat_interval_seconds": 30,
  "webhook_url": "https://my-service.com/tasks",  // optioneel
  "department_id": "uuid-of-department"            // optioneel
}
→ Response: { "agent_id": "ext-uuid", "api_key": "sk-...", "heartbeat_endpoint": "/api/v1/agents/ext-uuid/heartbeat" }

HEARTBEAT (elke 30s)
POST /api/v1/agents/{agent_id}/heartbeat
Headers: Authorization: Bearer sk-...
{
  "status": "idle" | "busy" | "error",
  "current_task_id": "uuid" | null,
  "progress": 0.75,                    // optioneel
  "metrics": {                          // optioneel
    "tasks_completed": 42,
    "avg_duration_seconds": 12.5
  }
}
→ Response: { "ack": true, "pending_tasks": [...] }

TAAK OPHALEN
GET /api/v1/agents/{agent_id}/tasks/next
→ Response: {
    "task_id": "uuid",
    "action": "analyze_supplier_contracts",
    "input": { ... },
    "goal_ancestry": {
      "mission": "Marktleider in duurzame retail",
      "strategic_goal": "Kosten verlagen 20%",
      "project_goal": "Supply chain optimalisatie",
      "task": "Leverancierscondities analyseren"
    },
    "sla_seconds": 300,
    "domain_pack": "logistics.global_route_shield"
  }

TAAK VOLTOOIEN
POST /api/v1/agents/{agent_id}/tasks/{task_id}/complete
{
  "status": "completed" | "failed",
  "output": { ... },
  "reasoning_trace": "..."       // voor OODA audit trail
}
```

#### 4.3.4 Integratie met bestaande AgentArchitectuur

```python
# Bestaande interne agent flow (ongewijzigd):
class EnhancedBaseAgent:
    async def process_task(self, task: TaskData) -> TaskResult

# Nieuwe bridge voor externe agents:
class ExternalAgentBridge(EnhancedBaseAgent):
    """
    Maakt een externe agent (heartbeat-based) bruikbaar als interne agent.
    De DomainPackOrchestrator ziet geen verschil.
    """
    async def process_task(self, task: TaskData) -> TaskResult:
        # 1. Dispatch taak naar externe agent (webhook of queue)
        # 2. Wacht op completion via heartbeat polling
        # 3. Return resultaat in standaard TaskResult format
        # 4. Respecteert SLA timeout uit DomainPack step
```

#### 4.3.5 Mapping naar bestaande code

| Nieuw Concept | Koppelt aan | Hoe |
|---|---|---|
| `ExternalAgent` model | `EnhancedBaseAgent` | Bridge pattern — DomainPackOrchestrator ziet geen verschil |
| Heartbeat endpoint | `router_registry.py` | Nieuwe router: `/api/v1/agents/external/` |
| Task dispatch | `DomainPackOrchestrator._run_single_step()` | Step met `runtime: "external"` dispatcht via bridge |
| Agent health | `SystemHealth` page | Externe agents verschijnen met heartbeat status |
| Governance | `PolicyEngine.validate_action()` | Externe agent acties doorlopen zelfde policy checks |
| Budget tracking | `BudgetManager` | Externe agents hebben eigen token/cost budgets |

---

### Feature 4: Board Governance (Menselijke Metafoor)

#### 4.4.1 Beschrijving

Een niet-technische **presentatielaag** bovenop de bestaande `PolicyEngine` die enterprise beslissingen presenteert als bedrijfsbeslissingen: "De board keurt goed", "HR-directeur escaleert naar CEO", "Budget overschrijding vereist CFO-goedkeuring".

> **Architectureel principe:** Board Governance is **uitsluitend een presentatie- en routeringslaag**. De `PolicyEngine` blijft de **enige bron van waarheid** voor enforcement. Board Governance vertaalt technische policy-uitkomsten naar bedrijfstaal en routeert approvals naar de juiste persoon — maar voegt **geen eigen enforcement-regels** toe. Dit voorkomt dat er twee parallelle governance-systemen ontstaan die semantisch kunnen losraken.
>
> ```
> PolicyEngine (ENFORCEMENT — single source of truth)
>     ↓ decision: requires_approval=true, risk_level=CRITICAL
> BoardService (PRESENTATIE — vertaling + routing)
>     ↓ vertaalt naar: "Board approval vereist van CFO"
>     ↓ routeert naar: user met RBAC role `finance_admin`
> BoardDecision (AUDIT — vastlegging van menselijke keuze)
>     ↓ decision fed back naar PolicyEngine als approval/rejection
> ```

#### 4.4.2 User Stories

| ID | Story | Prioriteit |
|---|---|---|
| US-4.1 | Als tenant admin wil ik een "Board of Directors" configureren met rollen (CEO, CFO, CTO, CHRO) zodat governance menselijk aanvoelt | P1 |
| US-4.2 | Als systeem wil ik CRITICAL policy violations presenteren als "Board approval vereist" i.p.v. technische foutmeldingen | P1 |
| US-4.3 | Als board member wil ik een approval queue zien met bedrijfscontext (niet technische details) | P1 |
| US-4.4 | Als systeem wil ik automatisch de juiste board member routeren op basis van department (Finance → CFO) | P2 |
| US-4.5 | Als board member wil ik agent "hiring" (activatie) en "firing" (deactivatie) goedkeuren | P2 |

#### 4.4.3 Mapping naar PolicyEngine

```
PolicyEngine (bestaand)               Board Governance (nieuw, bovenop)
─────────────────────                  ──────────────────────────────────
risk_level: CRITICAL          →        "Board approval vereist"
risk_level: HIGH              →        "Afdelingshoofd moet goedkeuren"
risk_level: MEDIUM            →        "Team lead notificatie"
risk_level: LOW               →        Automatisch goedgekeurd

requires_approval: true       →        Routed naar juiste board member
action_pattern: "budget_*"    →        CFO approval queue
action_pattern: "hire_agent"  →        Board vote (meerderheid)
action_pattern: "data_export" →        Compliance Officer review
```

#### 4.4.4 Board Rollen → RBAC Mapping

| Board Rol | RBAC Equivalent | Auto-route wanneer |
|---|---|---|
| CEO | `tenant_admin` | Cross-department conflicts, missie-wijzigingen |
| CFO | `finance_admin` | Budget overschrijdingen, cost > threshold |
| CTO | `tech_admin` | Externe agent registratie, infra changes |
| CHRO | `hr_admin` | Agent hiring/firing, team wijzigingen |
| Compliance Officer | `compliance_admin` | Data export, GDPR acties, audit triggers |

---

### Feature 5: Company Templates

#### 4.5.1 Beschrijving

Exporteerbare, deelbare bedrijfsstructuren die een complete configuratie bundelen: company model, afdelingen, doelen, geactiveerde Domain Packs, governance regels, budget allocaties, en externe agent configuraties. Met secret-scrubbing en collision handling.

#### 4.5.2 User Stories

| ID | Story | Prioriteit |
|---|---|---|
| US-5.1 | Als platform wil ik 10+ starter templates aanbieden (Retail MKB, Tech Startup, ZZP Freelancer, etc.) | P1 |
| US-5.2 | Als tenant admin wil ik mijn company configuratie exporteren als template | P2 |
| US-5.3 | Als tenant admin wil ik een template importeren en direct operationeel zijn | P1 |
| US-5.4 | Als systeem wil ik bij export automatisch secrets en tenant-specifieke data scrubben | P0 |
| US-5.5 | Als systeem wil ik bij import collisions detecteren en oplossen (bestaande packs, agents, etc.) | P1 |

#### 4.5.3 Template Structuur

```yaml
# company_template: retail_mkb_starter_v1.yaml
metadata:
  name: "Retail MKB Starter"
  version: 1
  sector: "retail"
  company_type: "mkb"
  description: "Complete setup voor retail MKB met sales, finance, en operations"

company:
  mission: "Groei realiseren door klantgerichte retail"
  departments:
    - name: "Sales"
      domain_packs:
        - mkb.digital_storefront
        - mkb.customer_pulse
        - sales.lead_enrichment
      budget_monthly_tokens: 500000
      board_member: "CEO"
    - name: "Finance"
      domain_packs:
        - mkb.zero_admin
        - finance.fraud_detection
      budget_monthly_tokens: 200000
      board_member: "CFO"
    - name: "Operations"
      domain_packs:
        - mkb.smart_retail
        - mkb.operations_flow
        - ops.last_mile
      budget_monthly_tokens: 300000
      board_member: "CEO"

goals:
  - type: strategic
    name: "Online omzet verdubbelen"
    department: "Sales"
    kpis: ["conversion_rate", "aov", "traffic"]
  - type: strategic
    name: "Operationele kosten -15%"
    department: "Operations"
    kpis: ["cost_per_order", "inventory_turns"]

governance:
  board:
    - role: CEO
      approval_threshold: "critical"
    - role: CFO
      approval_threshold: "budget_exceeded"
  policies:
    - pattern: "data_export"
      requires_approval: true
      approver: "CEO"

external_agents: []  # Geen externe agents in starter template
```

#### 4.5.4 Starter Templates (10+)

| Template | Type | Sector | Packs | Afdelingen |
|---|---|---|---|---|
| `retail_mkb_starter` | MKB | Retail | 8 | Sales, Finance, Ops |
| `tech_startup_lean` | MKB | Tech | 6 | Product, Engineering, Growth |
| `zzp_freelancer_pro` | ZZP | Divers | 5 | — (flat) |
| `consulting_firm` | MKB | Services | 7 | Client, Delivery, Finance |
| `ecommerce_scale` | Enterprise | Retail | 12 | Sales, Marketing, Logistics, Finance, CX |
| `healthcare_clinic` | MKB | Healthcare | 6 | Patient Care, Admin, Compliance |
| `manufacturing_ops` | Enterprise | Manufacturing | 10 | Production, QA, Supply Chain, Maintenance |
| `saas_company` | MKB | Tech | 9 | Product, Engineering, CS, Sales, Marketing |
| `legal_practice` | MKB | Legal | 5 | Client, Legal, Finance |
| `creative_agency` | MKB | Services | 7 | Creative, Account, Production |

---

### Feature 6: Simplified Onboarding ("Lite Mode")

#### 4.6.1 Beschrijving

Een vereenvoudigde onboarding flow die de drempel verlaagt voor MKB/ZZP-gebruikers. Geïnspireerd door Paperclip's `npx paperclipai onboard` — maar dan voor SanskritiSetu met full enterprise capabilities op de achtergrond.

#### 4.6.2 User Stories

| ID | Story | Prioriteit |
|---|---|---|
| US-6.1 | Als nieuwe gebruiker wil ik in 3 stappen operationeel zijn: (1) kies template, (2) pas aan, (3) start | P1 |
| US-6.2 | Als ZZP'er wil ik SanskritiSetu gebruiken zonder Docker/Redis/RabbitMQ op te zetten (hosted SaaS mode) | P2 |
| US-6.3 | Als systeem wil ik bij onboarding automatisch de company template instantiëren met alle packs, goals, en governance | P1 |
| US-6.4 | Als nieuwe gebruiker wil ik een guided tour die mijn bedrijfsstructuur uitlegt in niet-technische taal | P2 |

#### 4.6.3 Onboarding Flow

```
Stap 1: "Wat voor bedrijf heb je?"
  → Kies type: MKB / ZZP / Enterprise
  → Kies sector: Retail / Tech / Services / ...
  → Of: "Beschrijf je bedrijf in 1 zin" (AI matching naar template)

Stap 2: "Klopt dit organigram?"
  → Template-gebaseerd organigram tonen
  → Afdelingen toevoegen/verwijderen
  → Automatisch Domain Packs preview per afdeling

Stap 3: "Definieer je belangrijkste doel"
  → Company mission invullen
  → 1-3 strategic goals selecteren of typen
  → AI suggereert KPIs per goal

→ Company wordt aangemaakt met:
  - Alle matching Domain Packs geactiveerd
  - Goal hierarchy ingesteld
  - Board governance geconfigureerd
  - Budget allocaties per afdeling
  - Eerste workflows klaar om te draaien
```

---

## 5. Architectuur Design

### 5.1 Systeemarchitectuur (High-Level)

```
┌──────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + Vite)                       │
│  ┌────────────┐ ┌──────────────┐ ┌───────────┐ ┌──────────────┐ │
│  │ Company    │ │ Org Chart    │ │ Goal Tree │ │ Board        │ │
│  │ Setup      │ │ Builder      │ │ Dashboard │ │ Approval     │ │
│  │ Wizard     │ │ (ReactFlow)  │ │           │ │ Queue        │ │
│  └────────────┘ └──────────────┘ └───────────┘ └──────────────┘ │
│  ┌────────────┐ ┌──────────────┐ ┌───────────┐ ┌──────────────┐ │
│  │ External   │ │ Pack Selector│ │ Mission   │ │ Template     │ │
│  │ Agent Hub  │ │ (bestaand)   │ │ Control   │ │ Marketplace  │ │
│  │            │ │              │ │ (bestaand)│ │              │ │
│  └────────────┘ └──────────────┘ └───────────┘ └──────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                     API GATEWAY (FastAPI)                         │
│                                                                   │
│  /api/v1/companies/*          ← Company CRUD + templates          │
│  /api/v1/companies/{id}/org/* ← Org chart management              │
│  /api/v1/goals/*              ← Goal hierarchy CRUD               │
│  /api/v1/agents/external/*    ← Heartbeat protocol                │
│  /api/v1/board/*              ← Board governance approvals        │
│  /api/v1/templates/*          ← Company template marketplace      │
│  /api/v1/onboarding/*         ← Simplified onboarding wizard      │
│                                                                   │
│  (Bestaande endpoints ongewijzigd)                                │
│  /api/v1/agentic/*  /api/v1/procedures/*  /api/v1/auth/*  etc.   │
├──────────────────────────────────────────────────────────────────┤
│                     SERVICE LAYER                                 │
│                                                                   │
│  ┌───────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ CompanyService     │  │ GoalService      │  │ BoardService  │  │
│  │ - create_company() │  │ - create_goal()  │  │ - submit()    │  │
│  │ - activate_packs() │  │ - get_ancestry() │  │ - approve()   │  │
│  │ - export_template()│  │ - track_progress()│ │ - route()     │  │
│  └───────┬───────────┘  └────────┬─────────┘  └───────┬───────┘  │
│          │                       │                     │          │
│  ┌───────▼───────────┐  ┌───────▼──────────┐  ┌───────▼───────┐  │
│  │ ExternalAgentSvc   │  │ PackIntentMatcher│  │ PolicyEngine  │  │
│  │ - register()       │  │ (bestaand)       │  │ (bestaand)    │  │
│  │ - heartbeat()      │  │                  │  │ + board rules │  │
│  │ - dispatch_task()  │  │                  │  │               │  │
│  └───────┬───────────┘  └──────────────────┘  └───────────────┘  │
│          │                                                        │
│  ┌───────▼──────────────────────────────────────────────────────┐ │
│  │              ExternalAgentBridge                              │ │
│  │  Wraps external agents as EnhancedBaseAgent instances        │ │
│  │  → DomainPackOrchestrator ziet geen verschil                 │ │
│  └──────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│                     DATA LAYER                                    │
│  PostgreSQL: companies, departments, goals, external_agents,      │
│              board_decisions, company_templates                    │
│  Redis: heartbeat_status:{agent_id}, goal_progress_cache          │
│  (Bestaande tabellen ongewijzigd)                                 │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 Dependency Injection Integratie

Nieuwe services worden geregistreerd in de bestaande `Container`:

```python
# src/core/container.py — uitbreiding
class Container(DeclarativeContainer):
    # ... bestaande providers ...

    # Company Layer (nieuw)
    company_service = providers.Factory(
        CompanyService,
        db_manager=database_manager,
        pack_matcher=pack_intent_matcher,
        tenant_context=tenant_context,
    )
    goal_service = providers.Factory(
        GoalService,
        db_manager=database_manager,
        tenant_context=tenant_context,
    )
    external_agent_service = providers.Factory(
        ExternalAgentService,
        db_manager=database_manager,
        policy_engine=policy_engine,
        budget_manager=budget_manager,
        tenant_context=tenant_context,
    )
    board_service = providers.Factory(
        BoardService,
        policy_engine=policy_engine,
        tenant_context=tenant_context,
    )
```

### 5.3 Agent Bridge Architecture

```
                   DomainPackOrchestrator
                   (bestaand, ongewijzigd)
                          │
                   _run_single_step(step)
                          │
              ┌───────────┴───────────┐
              │                       │
    step.runtime == "internal"   step.runtime == "external"
              │                       │
     EnhancedBaseAgent         ExternalAgentBridge
     (bestaande agents)        (nieuw — wraps externe agent)
              │                       │
     Direct execution          ┌──────┴──────┐
                               │             │
                          Webhook        Task Queue
                          dispatch       dispatch
                               │             │
                          HTTP POST      Redis/RMQ
                          naar agent     message
                               │             │
                          Heartbeat      Heartbeat
                          polling        polling
                               │             │
                          TaskResult     TaskResult
```

### 5.4 Uniform Agent Execution Context (Canoniek Contract)

Alle agents — intern, extern, pack-gebaseerd, board-gerelateerd — ontvangen **exact hetzelfde** contextobject. Dit voorkomt dat interne agents, externe agents, packs en governance ieder met net andere contextvelden werken.

```python
# src/core/company/context.py

class GoalChain(BaseModel):
    """Immutable goal ancestry chain — altijd top-down van missie naar taak"""
    mission_id: Optional[UUID] = None
    mission_title: Optional[str] = None
    strategic_goal_id: Optional[UUID] = None
    strategic_goal_title: Optional[str] = None
    project_goal_id: Optional[UUID] = None
    project_goal_title: Optional[str] = None
    task_goal_id: Optional[UUID] = None
    task_goal_title: Optional[str] = None

    def is_complete(self) -> bool:
        """Retourneert True als minstens mission + current task aanwezig zijn"""
        return self.mission_id is not None and self.task_goal_id is not None

    def depth(self) -> int:
        """Aantal niveaus in de keten (0-4)"""
        return sum(1 for v in [self.mission_id, self.strategic_goal_id,
                               self.project_goal_id, self.task_goal_id] if v is not None)


class PolicyScope(BaseModel):
    """Governance context meegegeven aan elke agent"""
    risk_level: str                          # LOW, MEDIUM, HIGH, CRITICAL
    requires_approval: bool = False
    approval_board_role: Optional[str] = None  # CEO, CFO, CTO, CHRO, etc.
    allowed_actions: List[str] = []            # Whitelist van toegestane acties
    forbidden_actions: List[str] = []          # Blacklist van verboden acties


class BudgetScope(BaseModel):
    """Budget context per department/company"""
    monthly_token_budget: Optional[int] = None
    tokens_consumed_this_month: Optional[int] = None
    budget_remaining_pct: Optional[float] = None  # 0.0-1.0


class AgentExecutionContext(BaseModel):
    """
    HET canonieke contextobject voor elke agent execution.
    Wordt meegegeven aan zowel EnhancedBaseAgent.process_task()
    als ExternalAgentBridge.dispatch() en heartbeat task responses.

    Enforcement: Gouden Regel R1 — geen execution zonder dit object.
    """
    # Identiteit
    tenant_id: int
    company_id: Optional[UUID] = None
    company_type: Optional[str] = None        # mkb, zzp, enterprise
    sector: Optional[str] = None              # retail, tech, services, ...

    # Organisatie
    department_id: Optional[UUID] = None
    department_name: Optional[str] = None
    board_role: Optional[str] = None          # Verantwoordelijke board member

    # Workflow
    pack_id: Optional[UUID] = None
    pack_name: Optional[str] = None
    procedure_id: Optional[UUID] = None
    task_id: UUID                              # Altijd verplicht
    trace_id: UUID                             # OpenTelemetry trace ID

    # Doelketen (Gouden Regel R1)
    goal_chain: GoalChain = GoalChain()

    # Governance (Gouden Regel R3)
    policy_scope: PolicyScope = PolicyScope(risk_level="LOW")

    # Budget
    budget_scope: BudgetScope = BudgetScope()

    # SLA
    sla_seconds: Optional[int] = None

    # Degraded mode indicator
    is_degraded: bool = False                  # True als company_id of goal_chain ontbreekt

    def validate_completeness(self) -> tuple[bool, list[str]]:
        """
        Valideert of het contextobject compleet is.
        Retourneert (is_valid, missing_fields).
        Bij degraded mode: logt waarschuwing maar blokkeert niet.
        """
        missing = []
        if self.company_id is None:
            missing.append("company_id")
        if not self.goal_chain.is_complete():
            missing.append("goal_chain (incomplete)")
        if self.department_id is None:
            missing.append("department_id")

        is_valid = len(missing) == 0
        if not is_valid:
            self.is_degraded = True
        return is_valid, missing
```

**Gebruik in bestaande code (non-breaking):**

| Integratiepunt | Hoe `AgentExecutionContext` wordt meegegeven |
|---|---|
| `EnhancedBaseAgent.process_task(task)` | `task.context: AgentExecutionContext` — nieuw optioneel veld op `TaskData` |
| `ExternalAgentBridge.dispatch(task)` | Context wordt geserialiseerd in heartbeat task response |
| `DomainPackOrchestrator._run_single_step()` | Context gebouwd uit execution + goal + department, doorgegeven aan agent |
| `PolicyEngine.validate_action()` | `policy_scope` uit context wordt meegestuurd |
| `BoardService.submit()` | `goal_chain` + `budget_scope` uit context worden meegestuurd |
| Externe agent `GET /tasks/next` response | Volledig `AgentExecutionContext` als JSON in response body |

---

## 6. Data Models & Migraties

### 6.1 Nieuwe Database Modellen

```python
# src/core/company/models.py

class Company(Base):
    """Virtual company model — child of Tenant"""
    __tablename__ = "companies"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    company_type = Column(String(50), nullable=False)  # mkb, zzp, enterprise
    sector = Column(String(100), nullable=False)        # retail, tech, services, ...
    mission = Column(String(2000), nullable=True)
    config = Column(JSONB, nullable=False, default={})   # Additional company config
    template_id = Column(PG_UUID(as_uuid=True), nullable=True)  # Source template
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Department(Base):
    """Department within a Company — maps to Domain Pack categories"""
    __tablename__ = "departments"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, nullable=False, index=True)
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    parent_department_id = Column(PG_UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)  # Hiërarchie
    head_user_id = Column(PG_UUID(as_uuid=True), nullable=True)  # Afdelingshoofd
    board_role = Column(String(50), nullable=True)  # CEO, CFO, CTO, CHRO, etc.
    budget_monthly_tokens = Column(Integer, nullable=True)
    domain_pack_ids = Column(JSONB, nullable=False, default=[])  # Geactiveerde packs
    config = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Goal(Base):
    """Hierarchical goal model — mission → strategic → project → task"""
    __tablename__ = "goals"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, nullable=False, index=True)
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    parent_goal_id = Column(PG_UUID(as_uuid=True), ForeignKey("goals.id"), nullable=True, index=True)
    department_id = Column(PG_UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    goal_type = Column(String(50), nullable=False)  # mission, strategic, project, task
    title = Column(String(500), nullable=False)
    description = Column(String(2000), nullable=True)
    kpis = Column(JSONB, nullable=False, default=[])  # [{name, target, current, unit}]
    status = Column(String(50), nullable=False, default="active")  # active, completed, paused, cancelled
    progress_pct = Column(Integer, nullable=False, default=0)  # 0-100
    deadline = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExternalAgent(Base):
    """External agent registered via heartbeat protocol"""
    __tablename__ = "external_agents"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, nullable=False, index=True)
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    department_id = Column(PG_UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    name = Column(String(255), nullable=False)
    runtime = Column(String(50), nullable=False)  # python, node, shell, webhook, claude-code
    capabilities = Column(JSONB, nullable=False, default=[])
    webhook_url = Column(String(2000), nullable=True)
    api_key_hash = Column(String(255), nullable=False)  # bcrypt hash of agent API key
    heartbeat_interval_seconds = Column(Integer, nullable=False, default=30)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), nullable=False, default="registered")  # registered, active, idle, error, dead
    metrics = Column(JSONB, nullable=False, default={})  # tasks_completed, avg_duration, etc.
    config = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class BoardDecision(Base):
    """Board governance decision record"""
    __tablename__ = "board_decisions"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(Integer, nullable=False, index=True)
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    requested_by = Column(String(255), nullable=False)  # Agent ID of gebruiker
    board_role = Column(String(50), nullable=False)       # Naar welke board member
    action_type = Column(String(100), nullable=False)     # hire_agent, budget_override, data_export, etc.
    action_context = Column(JSONB, nullable=False, default={})  # Volledige context
    goal_id = Column(PG_UUID(as_uuid=True), ForeignKey("goals.id"), nullable=True)
    decision = Column(String(50), nullable=True)  # approved, rejected, deferred (NULL = pending)
    decided_by = Column(PG_UUID(as_uuid=True), nullable=True)  # User ID van beslisser
    reason = Column(String(2000), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class CompanyTemplate(Base):
    """Exportable/importable company blueprint"""
    __tablename__ = "company_templates"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    company_type = Column(String(50), nullable=False)
    sector = Column(String(100), nullable=False)
    description = Column(String(2000), nullable=True)
    template_definition = Column(JSONB, nullable=False)  # Volledige YAML-structuur als JSON
    is_platform_template = Column(Boolean, nullable=False, default=False)  # Door platform aangeboden
    contributed_by_tenant_id = Column(Integer, nullable=True)  # NULL voor platform templates
    usage_count = Column(Integer, nullable=False, default=0)
    rating_sum = Column(Integer, nullable=False, default=0)
    rating_count = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="active")  # active, draft, archived
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 6.2 Wijzigingen aan bestaande modellen

```python
# ProcedureExecution — nieuw veld toevoegen
# src/core/procedures/models.py
class ProcedureExecution(Base):
    # ... bestaande velden ...
    goal_id = Column(PG_UUID(as_uuid=True), ForeignKey("goals.id"), nullable=True)  # NIEUW

# DomainPack — nieuw veld toevoegen
class DomainPack(Base):
    # ... bestaande velden ...
    company_id = Column(PG_UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)  # NIEUW
```

### 6.3 Migratie Strategie

```
Migratie 1: create_company_tables
  - companies, departments, goals
  - Indexes op tenant_id voor alle tabellen
  - RLS policies voor tenant isolation

Migratie 2: create_external_agent_tables
  - external_agents
  - Index op (tenant_id, status) voor heartbeat queries

Migratie 3: create_board_governance_tables
  - board_decisions
  - Index op (tenant_id, company_id, decision) voor approval queue

Migratie 4: create_company_template_tables
  - company_templates

Migratie 5: alter_existing_tables
  - procedure_executions: ADD goal_id (nullable, FK)
  - domain_packs: ADD company_id (nullable, FK)
  - Geen breaking changes — beide nullable

Alle migraties zijn ADDITIVE (geen DROP, geen ALTER bestaande kolommen).
Bestaande data blijft ongewijzigd functioneren.
```

---

## 7. API Design

### 7.1 Nieuwe API Endpoints

#### Companies

| Method | Path | Beschrijving |
|---|---|---|
| `POST` | `/api/v1/companies` | Company aanmaken |
| `GET` | `/api/v1/companies` | Lijst companies voor tenant |
| `GET` | `/api/v1/companies/{id}` | Company details incl. org chart |
| `PUT` | `/api/v1/companies/{id}` | Company wijzigen |
| `DELETE` | `/api/v1/companies/{id}` | Company soft-delete |
| `POST` | `/api/v1/companies/{id}/activate-packs` | Trigger automatische pack activatie |
| `POST` | `/api/v1/companies/{id}/export` | Export als template |
| `POST` | `/api/v1/companies/import` | Import vanuit template |

#### Departments (Org Chart)

| Method | Path | Beschrijving |
|---|---|---|
| `POST` | `/api/v1/companies/{id}/departments` | Afdeling toevoegen |
| `GET` | `/api/v1/companies/{id}/departments` | Org chart ophalen (tree) |
| `PUT` | `/api/v1/departments/{id}` | Afdeling wijzigen |
| `DELETE` | `/api/v1/departments/{id}` | Afdeling verwijderen |
| `POST` | `/api/v1/departments/{id}/agents` | Agent toewijzen aan afdeling |

#### Goals

| Method | Path | Beschrijving |
|---|---|---|
| `POST` | `/api/v1/companies/{id}/goals` | Goal aanmaken |
| `GET` | `/api/v1/companies/{id}/goals` | Goal tree ophalen |
| `GET` | `/api/v1/goals/{id}` | Goal details met ancestry |
| `GET` | `/api/v1/goals/{id}/ancestry` | Volledige goal chain (mission → task) |
| `PUT` | `/api/v1/goals/{id}` | Goal wijzigen |
| `PUT` | `/api/v1/goals/{id}/progress` | Voortgang updaten |

#### External Agents (Heartbeat Protocol)

| Method | Path | Beschrijving |
|---|---|---|
| `POST` | `/api/v1/agents/external/register` | Agent registreren |
| `POST` | `/api/v1/agents/{id}/heartbeat` | Heartbeat sturen |
| `GET` | `/api/v1/agents/{id}/tasks/next` | Volgende taak ophalen |
| `POST` | `/api/v1/agents/{id}/tasks/{task_id}/complete` | Taak voltooien |
| `GET` | `/api/v1/agents/external` | Lijst externe agents |
| `DELETE` | `/api/v1/agents/external/{id}` | Agent deregistreren |

#### Board Governance

| Method | Path | Beschrijving |
|---|---|---|
| `GET` | `/api/v1/board/queue` | Approval queue voor huidige user |
| `POST` | `/api/v1/board/decisions/{id}/approve` | Goedkeuren |
| `POST` | `/api/v1/board/decisions/{id}/reject` | Afwijzen |
| `GET` | `/api/v1/board/decisions` | Beslissingshistorie |

#### Templates

| Method | Path | Beschrijving |
|---|---|---|
| `GET` | `/api/v1/templates/companies` | Beschikbare templates |
| `GET` | `/api/v1/templates/companies/{id}` | Template details |
| `POST` | `/api/v1/templates/companies/{id}/instantiate` | Template instantiëren |
| `POST` | `/api/v1/templates/companies/contribute` | Template bijdragen |

#### Onboarding

| Method | Path | Beschrijving |
|---|---|---|
| `GET` | `/api/v1/onboarding/templates` | Aanbevolen templates op basis van input |
| `POST` | `/api/v1/onboarding/ai-match` | AI matching: tekst → template suggestie |
| `POST` | `/api/v1/onboarding/complete` | Onboarding afronden (company + packs + goals aanmaken) |

### 7.2 Bestaande Endpoints — Wijzigingen

| Endpoint | Wijziging |
|---|---|
| `POST /api/v1/procedures/execute` | Optioneel `goal_id` parameter toevoegen |
| `POST /api/v1/agentic/generate` | `company_context` meegeven in pack matching |
| `GET /api/v1/agents` | Externe agents meenemen in response (met `source: "external"` flag) |
| `GET /api/v1/system/health` | Heartbeat status van externe agents meenemen |

---

## 8. Frontend Integratie

### 8.1 Nieuwe Pagina's

| Pagina | Route | Beschrijving |
|---|---|---|
| Company Setup Wizard | `/onboarding` | 3-staps onboarding flow |
| Company Dashboard | `/company` | Bedrijfsoverzicht met org chart |
| Org Chart Builder | `/company/org-chart` | ReactFlow-based organigram editor |
| Goal Tree | `/company/goals` | Hiërarchische doelen met voortgang |
| Board Approvals | `/board` | Approval queue voor board members |
| External Agent Hub | `/agents/external` | Registratie en monitoring externe agents |
| Template Marketplace | `/templates` | Browse en instantieer company templates |

### 8.2 Nieuwe Componenten

```
frontend/src/components/company/
├── CompanySetupWizard.tsx         # 3-staps onboarding
├── CompanyDashboard.tsx           # Bedrijfsoverzicht
├── OrgChartBuilder.tsx            # ReactFlow organigram
├── OrgChartNode.tsx               # Custom node voor afdeling
├── DepartmentPanel.tsx            # Afdeling detail sidebar
├── GoalTree.tsx                   # Hiërarchische doelen
├── GoalCard.tsx                   # Goal met progress bar
├── GoalAncestryBreadcrumb.tsx     # Mission → Strategic → Project → Task

frontend/src/components/board/
├── BoardApprovalQueue.tsx         # Approval items lijst
├── BoardDecisionCard.tsx          # Individueel approval item
├── BoardRoleAvatar.tsx            # CEO/CFO/CTO avatar

frontend/src/components/external-agents/
├── ExternalAgentHub.tsx           # Overzicht externe agents
├── AgentRegistrationForm.tsx      # Registratie wizard
├── HeartbeatMonitor.tsx           # Real-time heartbeat status
├── AgentHealthIndicator.tsx       # Groen/geel/rood status

frontend/src/components/templates/
├── TemplateMarketplace.tsx        # Browse templates
├── TemplatePreview.tsx            # Template detail met preview
├── TemplateInstantiateModal.tsx   # Importeer en pas aan
```

### 8.3 Wijzigingen aan bestaande componenten

| Component | Wijziging |
|---|---|
| `MissionControl` | Goal tree tab toevoegen, company context tonen |
| `PackExecutionMonitor` | Goal ancestry breadcrumb tonen boven execution |
| `DomainPackSelector` | Filter op department, toon "aanbevolen voor jouw bedrijf" |
| `SystemHealth` | Externe agent heartbeat status tonen |
| `Layout` | Company switcher in header (voor multi-company tenants) |
| `AgentDetailModal` | "Afdeling" en "Board member" velden tonen |

### 8.4 Nieuwe Zustand Stores

```typescript
// frontend/src/store/useCompanyStore.ts
interface CompanyStore {
  company: Company | null;
  departments: Department[];
  goals: Goal[];
  setCompany: (company: Company) => void;
  addDepartment: (dept: Department) => void;
  updateGoalProgress: (goalId: string, progress: number) => void;
}

// frontend/src/store/useBoardStore.ts
interface BoardStore {
  pendingDecisions: BoardDecision[];
  fetchQueue: () => Promise<void>;
  approve: (decisionId: string, reason?: string) => Promise<void>;
  reject: (decisionId: string, reason: string) => Promise<void>;
}

// frontend/src/store/useExternalAgentStore.ts
interface ExternalAgentStore {
  agents: ExternalAgent[];
  registerAgent: (config: AgentRegistration) => Promise<string>;
  fetchAgents: () => Promise<void>;
}
```

### 8.5 Nieuwe React Hooks

```typescript
// frontend/src/hooks/useCompany.ts           — Company CRUD + template operations
// frontend/src/hooks/useGoalAncestry.ts       — Goal chain ophalen voor context
// frontend/src/hooks/useBoardApprovals.ts     — Board approval queue + actions
// frontend/src/hooks/useExternalAgents.ts     — Agent registratie + heartbeat monitoring
// frontend/src/hooks/useOnboarding.ts         — Onboarding wizard state
// frontend/src/hooks/useOrgChart.ts           — Org chart CRUD + ReactFlow state
```

---

## 9. Migratie & Backward Compatibility

### 9.1 Zero Breaking Changes Garantie

| Aspect | Garantie |
|---|---|
| Bestaande API endpoints | Ongewijzigd, geen signature changes |
| Database schema | Alleen ADDITIVE changes (nieuwe tabellen, nullable kolommen) |
| Interne agents | Geen wijzigingen aan `EnhancedBaseAgent` contract |
| Domain Packs | `domain_packs.yaml` en `DomainPackRegistry` ongewijzigd |
| Frontend routes | Geen bestaande routes verwijderd of verplaatst |
| Environment variables | Geen bestaande vars verwijderd, nieuwe vars optioneel met defaults |

### 9.2 Gradual Adoption

Tenants hoeven de Company Layer niet te gebruiken. Alles werkt zoals voorheen totdat ze actief een Company aanmaken:

```
Tenant ZONDER Company (bestaand gedrag):
  → Domain Packs handmatig selecteren
  → Geen goal ancestry in executions
  → PolicyEngine zonder board metafoor
  → Geen externe agents

Tenant MET Company (na adoptie):
  → Automatische pack activatie op basis van afdelingen
  → Goal ancestry in elke execution
  → Board governance bovenop PolicyEngine
  → Externe agents via heartbeat
  → Company templates voor snelle setup
```

### 9.3 Data Migratie voor bestaande tenants

```
Optioneel (niet verplicht):
1. Tenant kiest "Upgrade naar Company" in settings
2. AI analyseert bestaande actieve Domain Packs
3. Suggereert company type, sector, en afdelingen
4. Genereert Company + Departments + Goals
5. Koppelt bestaande packs aan departments
6. Bestaande executions krijgen GEEN goal_id (nullable)
7. Nieuwe executions krijgen wel goal_id
```

---

## 10. Rollout Plan

### 10.0 MVP Scope & Phase Gates

De scope is bewust gefaseerd met **harde phase gates**. Fase 2+ wordt pas gestart na bewezen waarde van Fase 1. Dit voorkomt scope creep en zorgt dat het kernidee ("elke taak traceert naar het bedrijfsdoel") eerst werkt voordat complexere features worden toegevoegd.

#### MVP (Fase 1 — Must Ship)

| Feature | Scope | Waarom MVP |
|---|---|---|
| Company Model | CRUD + org chart (departments) | Fundament voor alles |
| Goal Ancestry | Hiërarchie + ancestry resolver + OODA integratie | Kernbelofte van de PRD |
| AgentExecutionContext | Canoniek contextobject in alle agent executions | Gouden Regel R1 enforcement |
| Pack Activation (basic) | Score model + audit trail + confidence thresholds | Gouden Regel R2 enforcement |
| Goal Alignment Validator | Pre-execution validatie (ALIGNED/DRIFT/MISALIGNED) | Kernbelofte operationeel maken |

#### Post-MVP (Fase 2+ — Alleen na bewezen MVP waarde)

| Feature | Phase Gate | Bewijs vereist voordat fase start |
|---|---|---|
| External Agents + Heartbeat | Fase 2 gate | MVP KPI: >= 20% tenants met Company, >= 15% executions met goal_id |
| Board Governance | Fase 3 gate | Fase 2 KPI: >= 1 externe agent succesvol in productie |
| Company Templates | Fase 3 gate | MVP KPI: onboarding time < 10 minuten zonder template |
| Template Marketplace | Fase 3 gate | >= 5 tenants hebben company export gebruikt |
| Simplified Onboarding | Fase 4 gate | >= 3 templates beschikbaar en getest |

> **Consequentie:** Als MVP KPIs na 6 weken niet gehaald worden, wordt Fase 2 uitgesteld en wordt eerst geïnvesteerd in MVP-adoptie. Features worden niet gebouwd op hoop — alleen op bewezen behoefte.
>
> ⚠️ **BLOCKER:** Fase 1 kan pas starten nadat **Fase 6.2 (Orphaned Services Cleanup)** en **Fase 6.3 (WebSocket Config & Health Checks)** zijn voltooid. Deze cleanups zijn noodzakelijk voor stabiele Company Layer infra. Status: beide fases zijn nog open task descriptions (SPRINT2-6_SUMMARY.md: 2026-02-25).

### Fase 1: Foundation (Sprint 7-8, 4 weken)

| Week | Deliverable | Owner |
|---|---|---|
| W1 | Database modellen + migraties (Company, Department, Goal) | Backend |
| W1 | Company CRUD API endpoints | Backend |
| W2 | Goal hierarchy API + ancestry resolver | Backend |
| W2 | Company Setup Wizard (frontend) | Frontend |
| W3 | Org Chart Builder met ReactFlow | Frontend |
| W3 | Goal Tree component + Mission Control integratie | Frontend |
| W4 | Integratie tests + E2E onboarding flow | QA |

**Exit criteria:** Een tenant kan een company aanmaken met afdelingen en doelen. Goal ancestry wordt meegegeven bij procedure executions.

### Fase 2: Open Ecosystem (Sprint 9-10, 4 weken)

| Week | Deliverable | Owner |
|---|---|---|
| W5 | ExternalAgent model + heartbeat endpoints | Backend |
| W5 | ExternalAgentBridge → DomainPackOrchestrator integratie | Backend |
| W6 | External Agent Hub (frontend) | Frontend |
| W6 | HeartbeatMonitor real-time WebSocket | Frontend |
| W7 | Python SDK voor externe agent registratie | Backend |
| W7 | Automatische pack activatie bij department aanmaak | Backend |
| W8 | Security audit heartbeat protocol + penetration test | Security |

**Exit criteria:** Een externe Python script kan registreren, heartbeats sturen, taken ontvangen, en resultaten terugsturen. Het draait naadloos in een Multi-Pack Assembly naast interne agents.

### Fase 3: Governance & Templates (Sprint 11-12, 4 weken)

| Week | Deliverable | Owner |
|---|---|---|
| W9 | Board Governance service + PolicyEngine bridge | Backend |
| W9 | Board Approval Queue (frontend) | Frontend |
| W10 | Company Template export/import | Backend |
| W10 | Template Marketplace (frontend) | Frontend |
| W11 | 10 starter templates (zie §4.5.4) | Product + Backend |
| W11 | Simplified onboarding wizard | Frontend |
| W12 | Full regression testing + performance benchmarks | QA |

**Exit criteria:** Board governance presenteert approvals in bedrijfstaal. 10 templates beschikbaar. Onboarding van template naar operationeel in < 5 minuten.

### Fase 4: Polish & Scale (Sprint 13, 2 weken)

| Week | Deliverable | Owner |
|---|---|---|
| W13 | AI-powered template matching ("beschrijf je bedrijf") | Backend |
| W13 | Goal-based ROI dashboards | Frontend |
| W14 | Documentation, API docs, SDK docs | Docs |
| W14 | Production deployment + monitoring | DevOps |

**Totale doorlooptijd: 14 weken (3.5 maanden)**

### 10.5 Meetbare Acceptatiecriteria per P0 Feature

Elke P0 feature heeft harde, testbare criteria die bepalen of de feature "af" is:

#### AC-1: Company Model (P0)

| # | Criterium | Verificatie |
|---|---|---|
| AC-1.1 | `POST /api/v1/companies` retourneert 201 met company_id binnen 500ms | Integration test |
| AC-1.2 | Company met 5 departments aanmaken duurt < 2s end-to-end | Performance test |
| AC-1.3 | Org chart GET retourneert correcte tree-structuur (parent-child relaties) | Unit test |
| AC-1.4 | Tenant A kan company van tenant B niet zien of wijzigen | Security test |
| AC-1.5 | Company zonder departments aanmaken is valide (ZZP use case) | Unit test |

#### AC-2: Goal Ancestry (P0)

| # | Criterium | Verificatie |
|---|---|---|
| AC-2.1 | `GET /goals/{id}/ancestry` retourneert volledige chain (mission→task) binnen 10ms | Performance test |
| AC-2.2 | Goal ancestry is aanwezig in `AgentExecutionContext` bij elke `process_task()` call | Integration test |
| AC-2.3 | Ancestry cache invalidatie werkt correct bij goal update | Unit test |
| AC-2.4 | Goal tree visualisatie toont max 4 niveaus met correcte progress rollup | E2E test (Playwright) |
| AC-2.5 | ProcedureExecution met goal_id bevat volledige goal_chain in audit_trail | Integration test |

#### AC-3: AgentExecutionContext (P0)

| # | Criterium | Verificatie |
|---|---|---|
| AC-3.1 | Intern agent ontvangt `AgentExecutionContext` met alle verplichte velden | Unit test |
| AC-3.2 | Extern agent `GET /tasks/next` response bevat volledige `AgentExecutionContext` als JSON | Integration test |
| AC-3.3 | Context met ontbrekende `company_id` markeert `is_degraded=true` en logt metric | Unit test |
| AC-3.4 | `validate_completeness()` retourneert correcte missing fields lijst | Unit test |
| AC-3.5 | Bestaande agents zonder Company Layer werken ongewijzigd met degraded context | Regression test |

#### AC-4: Pack Activation (P0)

| # | Criterium | Verificatie |
|---|---|---|
| AC-4.1 | Bij department "Sales" + type "mkb" worden >= 2 packs automatisch geactiveerd (score >= 0.70) | Integration test |
| AC-4.2 | Elke activatie genereert `PackActivationResult` met `match_reason` en `confidence` | Unit test |
| AC-4.3 | Pack met score 0.50-0.69 verschijnt als suggestie, NIET als auto-activatie | Unit test |
| AC-4.4 | Audit trail bevat volledige score breakdown per pack per department | Integration test |
| AC-4.5 | User kan auto-geactiveerde pack handmatig deactiveren | E2E test |

#### AC-5: Goal Alignment Validator (P0)

| # | Criterium | Verificatie |
|---|---|---|
| AC-5.1 | Actie aligned met goal chain (score >= 0.6) retourneert ALIGNED en procedeert | Unit test |
| AC-5.2 | Actie met score 0.3-0.59 retourneert DRIFT_WARNING, logt metric, en procedeert | Unit test |
| AC-5.3 | Actie met score < 0.3 retourneert MISALIGNED en **blokkeert** execution | Unit test |
| AC-5.4 | MISALIGNED actie wordt geëscaleerd naar BoardService (als board geconfigureerd) | Integration test |
| AC-5.5 | Degraded mode (geen goal chain) retourneert DRIFT_WARNING, niet MISALIGNED | Unit test |

---

## 11. Testing Strategie

### 11.1 Nieuwe Test Suites

```
tests/
├── unit/
│   ├── company/
│   │   ├── test_company_service.py          # Company CRUD + template instantiation
│   │   ├── test_goal_service.py             # Goal hierarchy + ancestry resolver
│   │   ├── test_department_service.py       # Department CRUD + pack activation
│   │   └── test_board_service.py            # Board routing + approval logic
│   ├── external_agents/
│   │   ├── test_heartbeat_protocol.py       # Heartbeat validation + timeout
│   │   ├── test_external_agent_bridge.py    # Bridge → DomainPackOrchestrator
│   │   └── test_task_dispatch.py            # Webhook + queue dispatch
│   └── templates/
│       ├── test_template_export.py          # Export met secret scrubbing
│       └── test_template_import.py          # Import met collision handling
├── integration/
│   ├── test_company_onboarding_flow.py      # Template → Company → Packs → Goals
│   ├── test_external_agent_e2e.py           # Register → Heartbeat → Task → Complete
│   ├── test_goal_ancestry_in_execution.py   # Execution draagt goal chain mee
│   ├── test_board_approval_flow.py          # PolicyEngine → Board → Approval → Execute
│   └── test_mixed_agent_workflow.py         # Interne + externe agents in 1 pack
├── e2e/
│   ├── test_company_setup_wizard.py         # Playwright: volledige onboarding
│   └── test_board_approval_ui.py            # Playwright: approve/reject flow
└── security/
    ├── test_external_agent_isolation.py     # Externe agent kan niet cross-tenant
    ├── test_heartbeat_auth.py               # Alleen geauthenticeerde heartbeats
    ├── test_template_secret_scrubbing.py    # Geen secrets in exports
    └── test_board_rbac.py                   # Alleen board members kunnen approven
```

### 11.2 Test Coverage Targets

| Module | Target | Rationale |
|---|---|---|
| Company Service | 95% | Core business logic |
| Goal Service | 95% | Core business logic |
| External Agent Service | 98% | Security-critical (open protocol) |
| Board Service | 95% | Governance-critical |
| Template Export/Import | 95% | Data integrity |
| Heartbeat Protocol | 98% | External-facing API |
| Frontend components | 80% | UI complexity |

### 11.3 Bestaande Tests — Regression

Alle bestaande tests MOETEN blijven slagen na integratie:
- `pytest tests/unit/ -v` → 0 failures
- `pytest tests/integration/ -v` → 0 failures
- `npm run test` (frontend) → 0 failures

---

## 12. Security & Compliance

### 12.1 Heartbeat Protocol Security

| Risico | Mitigatie |
|---|---|
| Ongeautoriseerde agent registratie | Alleen tenant admins kunnen agents registreren. API key wordt eenmalig getoond. |
| API key leakage | Keys worden bcrypt-gehasht opgeslagen. Rate limiting op heartbeat endpoint. |
| Spoofed heartbeats | Elke heartbeat gevalideerd met API key + tenant_id binding. |
| Malicious task output | Output doorloopt `PolicyEngine.validate_action()` voordat het wordt verwerkt. |
| DDoS via heartbeat endpoint | Rate limiting: max 10 heartbeats/minuut per agent. IP-based throttling. |
| Cross-tenant access | `ExternalAgent.tenant_id` enforced op alle queries. RLS policies op tabel. |

### 12.2 Template Security

| Risico | Mitigatie |
|---|---|
| Secrets in export | Automated scrubbing van: API keys, wachtwoorden, tokens, webhook URLs met credentials |
| Malicious template import | Template validation: schema check, size limits, geen executable code |
| Template injection | Template definitions zijn declaratief (YAML/JSON), geen code execution |

### 12.3 Board Governance Security

| Risico | Mitigatie |
|---|---|
| Unauthorized approvals | Board role → RBAC mapping enforced. Alleen assigned board members kunnen approven. |
| Approval bypass | `BoardService.approve()` valideert dat beslisser het juiste RBAC-recht heeft. |
| Audit trail | Elke board decision wordt gelogd met actor, timestamp, en reason. |

### 12.4 Compliance Impact

| Compliance Framework | Impact | Actie |
|---|---|---|
| GDPR | Externe agents verwerken mogelijk persoonsgegevens | Data Processing Agreement template voor externe agents |
| EU AI Act | Externe agents zijn onderdeel van AI-systeem | Audit logging voor alle externe agent acties |
| SOC2 | Nieuw aanvalsoppervlak (heartbeat API) | Penetration test op heartbeat endpoints |

---

## 13. Success Metrics & KPIs

### 13.1 Adoptie Metrics

| KPI | Baseline | Target (3 maanden na launch) | Meetmethode |
|---|---|---|---|
| % tenants met Company | 0% | 40% | `SELECT COUNT(DISTINCT tenant_id) FROM companies` |
| Gemiddeld aantal departments per company | 0 | 3.5 | `AVG(departments per company)` |
| % executions met goal_id | 0% | 25% | `WHERE goal_id IS NOT NULL` |
| Externe agents geregistreerd | 0 | 50+ | `COUNT(*) FROM external_agents` |
| Template instantiations | 0 | 100+ | `SUM(usage_count) FROM company_templates` |
| Board decisions per week | 0 | 200+ | `COUNT(*) FROM board_decisions per week` |

### 13.2 Performance Metrics

| KPI | Target | Meetmethode |
|---|---|---|
| Heartbeat latency (p95) | < 50ms | Prometheus histogram |
| Goal ancestry lookup | < 10ms | Prometheus histogram |
| Company creation (incl. pack activation) | < 3s | Prometheus histogram |
| Template instantiation | < 5s | Prometheus histogram |
| External agent task dispatch | < 200ms | Prometheus histogram |

### 13.3 Business Metrics

| KPI | Target | Rationale |
|---|---|---|
| Onboarding time (template → operational) | < 5 minuten | Verlaagde drempel voor MKB/ZZP |
| Pack activation rate (auto vs manual) | 60% auto | Company-based pack matching werkt |
| External agent uptime | > 99% | Heartbeat protocol is betrouwbaar |
| Board approval turnaround time | < 4 uur | Governance blokkeert niet |

### 13.4 Goal Focus Metrics (Doelbesef)

Deze metrics meten of het systeem daadwerkelijk het bedrijfsdoel als stuurmechanisme gebruikt — het kernidee van deze PRD. Zonder deze metrics kan het platform technisch snel en populair zijn, maar toch inhoudelijk het doelbesef verliezen.

| KPI | Baseline | Target (3 maanden) | Meetmethode | Alarm threshold |
|---|---|---|---|---|
| % taken met volledige context (`is_degraded=false`) | 0% | 70% | `AgentExecutionContext.is_degraded` counter | < 50% na 2 maanden |
| % beslissingen met traceerbare goal-alignment score | 0% | 60% | `goal_alignment_score IS NOT NULL` in audit trail | < 40% na 2 maanden |
| Gemiddelde goal alignment score | n/a | >= 0.65 | `AVG(goal_alignment_score)` per week | < 0.50 gemiddeld |
| % MISALIGNED acties dat daadwerkelijk geëscaleerd wordt | n/a | 100% | `MISALIGNED` events vs `BoardDecision` count | < 90% |
| % pack activaties met complete audit trail (R2) | 0% | 100% | `PackActivationResult` records vs activations | < 95% |
| % governance beslissingen met goal + budget context (R3) | 0% | 100% | `BoardDecision` records met non-null `goal_id` en `budget_impact` | < 90% |
| Goal ancestry depth per execution (gem.) | 0 | >= 2.5 | `AVG(GoalChain.depth())` | < 1.5 |

> **Operationeel:** Deze metrics worden als Prometheus gauges/histogrammen geëxporteerd en verschijnen op een dedicated "Goal Focus" dashboard in Grafana. Een weekelijkse alert gaat af als 3+ metrics onder hun alarm threshold zakken.

---

## 14. Risico's & Mitigaties

| # | Risico | Impact | Kans | Mitigatie |
|---|---|---|---|---|
| R1 | Company Layer voegt te veel complexiteit toe voor bestaande gebruikers | Hoog | Laag | Volledig optioneel — bestaand gedrag ongewijzigd |
| R2 | Externe agents introduceren security vulnerabilities | Hoog | Middel | Dedicated security sprint, penetration testing, rate limiting |
| R3 | Heartbeat protocol schaalt niet bij 1000+ externe agents | Middel | Middel | Redis-based heartbeat tracking, async processing |
| R4 | Goal ancestry vertraagt OODA execution | Middel | Laag | Gecached in Redis, lazy loading, max 4 levels diep |
| R5 | Board governance wordt als overhead ervaren | Middel | Middel | Configureerbaar per tenant — kan uitgeschakeld worden |
| R6 | Template marketplace krijgt lage adoptie | Laag | Middel | Start met 10 high-quality platform templates |
| R7 | Breaking changes door database migraties | Hoog | Laag | Alleen additive changes, geen DROP/ALTER bestaande kolommen |
| R8 | Frontend performance bij grote org charts | Middel | Middel | ReactFlow virtualization, max 50 nodes in view |

---

## 15. Appendix

### 15.1 Paperclip AI Referenties

- [Paperclip GitHub Repository](https://github.com/paperclipai/paperclip)
- [Paperclip Website](https://paperclip.ing/)
- [Paperclip Core Concepts](https://github.com/paperclipai/paperclip/blob/master/docs/start/core-concepts.md)
- [VibeSparking Analysis](https://www.vibesparking.com/en/blog/ai/agent-orchestration/2026-03-05-paperclip-open-source-orchestration-zero-human-companies/)
- [Flowtivity Zero-Human Companies](https://flowtivity.ai/blog/zero-human-company-paperclip-ai-agent-orchestration/)

### 15.2 Bestaande SanskritiSetu Documentatie

- `CLAUDE.md` — Project conventions en commands
- `AGENTS.md` — Agent architectuur en project guide
- `docs/FOCUS_BUILDER_PRD_v2.0.md` — FocusBuilder PRD
- `docs/PACK_INTELLIGENCE_SYSTEM.md` — Pack Intelligence System
- `config/domain_packs.yaml` — 80+ Domain Pack definities
- `config/agent_catalog_schema.json` — Agent catalog structuur

### 15.3 Glossary

| Term | Definitie |
|---|---|
| **Company** | Virtueel bedrijfsmodel binnen een tenant, met organigram en doelen |
| **Department** | Afdeling binnen een Company, gekoppeld aan Domain Packs |
| **Goal Ancestry** | Hiërarchische doelketen: Mission → Strategic → Project → Task |
| **Heartbeat Protocol** | Open protocol waarmee externe agents communiceren met het platform |
| **Board Governance** | Niet-technische governance-metafoor bovenop PolicyEngine |
| **Company Template** | Exporteerbare bedrijfsstructuur die packs, goals, en config bundelt |
| **External Agent** | Agent die buiten SanskritiSetu draait maar via heartbeat meedoet |
| **ExternalAgentBridge** | Adapter die externe agents als interne agents presenteert |
| **Pack Activation** | Automatisch activeren van Domain Packs op basis van bedrijfsstructuur |
| **AgentExecutionContext** | Canoniek contextobject dat ELKE agent (intern + extern) ontvangt bij task execution |
| **GoalChain** | Immutable doelketen (mission → strategic → project → task) binnen AgentExecutionContext |
| **Goal Alignment Validator** | Pre-execution validatie die checkt of een actie past bij de actieve goal chain |
| **PackActivationResult** | Auditeerbaar resultaat van pack matching met score, reden, en confidence |
| **Gouden Regels** | 3 architecturele invarianten die doelbesef afdwingen (R1: context, R2: uitlegbare match, R3: governance+doel) |
| **Phase Gate** | Harde voorwaarde (bewezen KPI) die gehaald moet worden voordat de volgende fase start |

### 15.4 Open Vragen

| # | Vraag | Eigenaar | Deadline |
|---|---|---|---|
| Q1 | Willen we Paperclip's TypeScript SDK wrappen of een eigen Python SDK schrijven? | Engineering | Fase 2 start |
| Q2 | Hoe diep integreren we goal ancestry in de CVA chat interface? | Product | Fase 1 start |
| Q3 | Moeten we een "lite mode" (embedded SQLite) ondersteunen voor ZZP? | Architecture | Fase 4 |
| Q4 | Hoe gaan we om met externe agents die GDPR-gevoelige data verwerken? | Legal | Fase 2 start |
| Q5 | Willen we Paperclip's company template format adopteren voor interoperabiliteit? | Product | Fase 3 start |

---

*Dit document is een levend document en wordt bijgewerkt naarmate de implementatie vordert.*

**Goedkeuring vereist van:**
- [ ] Product Owner
- [ ] Lead Architect
- [ ] Security Lead
- [ ] Frontend Lead
- [ ] Backend Lead
