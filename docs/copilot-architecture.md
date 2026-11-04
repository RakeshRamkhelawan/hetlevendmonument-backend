# Co-Pilot Architectuur — Het Ontwerp

**Project:** SanskritiSetu — Enterprise AI Agent Operating System
**Document type:** Comprehensive design document
**Status:** Accepted — 2026-05-23 | Sprint 3 productie-hardening afgerond 2026-05-24; Sprint 4 dag 1 (CopilotService core + LLMHandler + ProposalBuilder + schemas + protocols + complete_json overrides) afgerond 2026-05-24
**Bijbehorend ADR:** [ADR-027 — Co-Pilot met Agent Council](adr/027-copilot-agent-council.md)
**Bijbehorend sprintplan:** [docs/copilot-sprint-plan.md](copilot-sprint-plan.md)
**Auditbron:** [docs/copilot-feature-context.md](copilot-feature-context.md)

---

## Hoe je dit document leest

Dit document is geschreven om twee soorten lezers te bedienen:

- **De solo founder** die wil weten hoe het systeem werkt, wat het kost, en wat het verkoopt. Lees hoofdstuk 1, 2, 3 en 11.
- **De ontwikkelaar** (Claude, Gemini, of mens) die de code moet schrijven. Lees hoofdstuk 4 t/m 10 — daar staat de uitgekauwde architectuur met datastructuren, API-contracten en flow-diagrammen.

Beide groepen krijgen dezelfde inhoud, in oplopende mate van technisch detail.

---

## Inhoudsopgave

1. [De visie in één pagina](#1-de-visie-in-één-pagina)
2. [De Agent Council uitgelegd](#2-de-agent-council-uitgelegd)
3. [Wat het verkoopt](#3-wat-het-verkoopt)
4. [De Co-Pilot Service — geconsolideerde architectuur](#4-de-co-pilot-service--geconsolideerde-architectuur)
5. [De Council in detail — de zeven Officers](#5-de-council-in-detail--de-zeven-officers)
6. [Beslissingsflow van begin tot eind](#6-beslissingsflow-van-begin-tot-eind)
7. [Audit, hash chain en bewaartermijnen](#7-audit-hash-chain-en-bewaartermijnen)
8. [Proactieve patronen — Fase 1](#8-proactieve-patronen--fase-1)
9. [Notificatie UX en het 25-budget](#9-notificatie-ux-en-het-25-budget)
10. [Integratie met bestaande componenten](#10-integratie-met-bestaande-componenten)
11. [API surface en frontend touchpoints](#11-api-surface-en-frontend-touchpoints)
12. [Testen, observability en deploy](#12-testen-observability-en-deploy)
13. [Roadmap (Fase 2+)](#13-roadmap-fase-2)

---

## 1. De visie in één pagina

De Co-Pilot van SanskritiSetu is geen knop in de hoek. Het is een **digitale collega** die altijd meekijkt, de hele applicatie kent, jouw persoonlijke patronen leert (via de Digital Twin uit ADR-025), en die proactief meldingen geeft als hij iets opmerkt. Hij doet niets zonder dat een **interne raad van zeven specialisten** — de Agent Council — heeft beslist of het mag, of het aangepast moet, of er menselijke toestemming bij hoort, of dat het in z'n geheel niet mag.

### Vier vormen waarin de gebruiker hem ontmoet

| Interface | Modus | Voorbeeld |
|-----------|-------|-----------|
| **Cmd+K Command Palette** | One-shot | "Ga naar workflow X" |
| **Sidebar AICopilotPanel** | Multi-turn chat | "Help me brainstormen over donor-churn" |
| **Focus Builder Copilot** | Inline genereren | "Maak een workflow voor X" |
| **Proactieve signalen** | Push (max 25/dag) | "Agent X faalt 10x — kijken?" |

Alle vier sturen hun voorstellen door **dezelfde Council**. Eén brein, vier gezichten.

### Vijf eigenschappen die hem onderscheiden

1. **Volledige platformkennis** — kent élke route, élke feature, élke agent in het systeem.
2. **Persoonlijk geheugen** — onthoudt jouw gewoontes via de Digital Twin (met consent, ADR-026).
3. **Proactief** — wacht niet op je vraag; let zelf op falende agents, gevaarlijke acties, herhalende patronen.
4. **Compliance by design** — élke beslissing wordt gewogen door de Council en gelogd voor AI Act / GDPR / ISO 42001.
5. **Uitlegbaar** — bij elke suggestie kan de gebruiker doorklikken naar "waarom raadde je dit aan?"

---

## 2. De Agent Council uitgelegd

Stel je voor: voordat de Co-Pilot iets aan jou laat zien, vergadert er een interne raad van zeven specialisten. Elk specialist kijkt naar één aspect:

| Officer | Houdt het oog op | Mag... |
|---------|------------------|--------|
| **Compliance Officer** | AI Act, GDPR, ISO 42001 | Definitief weigeren |
| **Privacy Officer** | Persoonsgegevens, consent | Definitief weigeren |
| **Security Officer** | Tool-misbruik, prompt-injectie | Definitief weigeren |
| **Risk Officer** | "Hoe groot is de impact?" | Menselijke toestemming eisen |
| **Ethics Officer** | Bias, fairness, transparantie | Aanpassing eisen |
| **Resource Officer** | Kosten, rate limits, notificatie-budget | Uitstellen |
| **Audit Officer** | Alles correct vastleggen | Niets blokkeren, alleen loggen |

De Council vergadert in **milliseconden**, niet in dagen. Per voorstel: elke Officer kijkt parallel, geeft één van vijf antwoorden (goedkeuren / aanpassen / menselijke toestemming / uitstellen / weigeren), en de Coordinator volgt strikte regels om tot één eindbesluit te komen.

### De regel: strengste eis wint

```
Eén veto = stop
Geen veto + iemand wil HITL = HITL
Geen veto + iemand wil uitstel = uitstel
Geen veto + iemand wil aanpassing = aanpassen + herzien
Anders = goedkeuren
```

De Audit Officer praat altijd als laatste, en hij blokkeert nooit — maar zonder zijn handtekening (log in de hash-keten) wordt er niets uitgevoerd. Dat heet **fail-secure**: bij twijfel of storing, niet doen.

---

## 3. Wat het verkoopt

Vanaf **2 augustus 2026** is de EU AI Act afdwingbaar. Bedrijven die AI inzetten moeten kunnen aantonen dat:

- elke AI-beslissing automatisch is gelogd (art. 12)
- de gebruiker weet dat hij met AI praat (art. 50)
- er een menselijke interventie mogelijk is (GDPR art. 22)
- de gebruiker op verzoek uitleg krijgt over de logica (GDPR art. 13-15)

De meeste concurrenten denken hierover ná het inkleuren van hun feature. Wij hebben dit in de **architectuur** zitten — letterlijk een raad die meekijkt en signeert. Dat is een verkoopverhaal voor elke compliance officer, juridisch adviseur, en CTO in Europa.

### Concrete sales-haakjes

1. **"Live demo: hier ziet u waarom onze AI dit zojuist heeft voorgesteld."** — open de AuditViewer, scroll terug, klik op een beslissing, zie alle zeven Officer-uitspraken plus de hash-keten-validatie.
2. **"Onze AI weigert zichzelf als hij over de grens dreigt te gaan."** — toon een veto-scenario: gebruiker vraagt om PII-export, Privacy Officer veto't, transparant gelogd.
3. **"Audit-rapportage met één klik."** — genereer een PDF met alle Council-besluiten over een tijdsbereik, gegroepeerd per regelgevingsartikel.
4. **"AI Act compliance from day one."** — terwijl concurrenten in Q3 2026 nog hun logging-laag bouwen, hebben jouw klanten al een werkend systeem.

### Markt-positie

De features die de Council standaard biedt — automatische logging, right-to-explanation API, tamper-evident hash chain, granulaire consent gates — zijn precies wat consultants nu voor €50k-€200k per opdracht inbouwen bij ondernemingen. Door dit als ingebouwde feature aan te bieden, claim je dit budget in een SaaS-prijs.

---

## 4. De Co-Pilot Service — geconsolideerde architectuur

De huidige codebase heeft drie versnipperde Co-Pilot endpoints. Wij consolideren naar één service-laag met drie transports.

### Doelarchitectuur

```
┌────────────────────────────────────────────────────────────────┐
│                      FRONTEND LAYER                            │
│                                                                │
│  CommandPalette (Cmd+K)   AICopilotPanel (sidebar)            │
│         │                          │                           │
│         │                          │                           │
│  FocusBuilder Copilot     Proactive Signal UI                 │
│         │                          │                           │
└─────────┼──────────────────────────┼───────────────────────────┘
          │                          │
          │ HTTP/SSE                 │ WebSocket
          │                          │
┌─────────┴──────────────────────────┴───────────────────────────┐
│                      TRANSPORT LAYER                           │
│                                                                │
│  POST /api/v1/copilot/turn (one-shot, SSE optional)           │
│  WS   /ws/copilot/chat       (multi-turn streaming)           │
│  POST /api/v1/copilot/proactive/{signal_id}/respond           │
│  GET  /api/v1/copilot/audit/{decision_id}  (right to explain) │
│  GET  /api/v1/copilot/notifications/preferences               │
│  PUT  /api/v1/copilot/notifications/preferences               │
└─────────────────────┬──────────────────────────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────────────────────────┐
│                    COPILOT SERVICE                             │
│                                                                │
│  1. Authenticate + extract tenant_id from JWT                  │
│  2. Rate limit (per user + per tenant)                         │
│  3. Build Proposal (NLU + context snapshot)                    │
│  4. Submit to Agent Council                                    │
│  5. On APPROVED:   execute via ToolBroker (ADR-015)            │
│     On MODIFIED:   apply mods, re-submit to Council            │
│     On HITL:       persist + notify, await OversightGate       │
│     On DEFERRED:   schedule retry                              │
│     On BLOCKED:    return generic refusal to user              │
└─────────────────────┬──────────────────────────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────────────────────────┐
│                   AGENT COUNCIL                                │
│                                                                │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────┐│
│  │Compliance│  │Privacy │  │Security│  │ Risk   │  │ Ethics ││
│  │ Officer │  │Officer │  │Officer │  │Officer │  │Officer ││
│  └────┬────┘  └───┬────┘  └───┬────┘  └───┬────┘  └───┬────┘│
│       │           │            │           │           │      │
│       └───────────┴────────────┼───────────┴───────────┘      │
│                                │                              │
│                          ┌─────▼──────┐                       │
│                          │ Resource   │                       │
│                          │ Officer    │                       │
│                          └─────┬──────┘                       │
│                                │                              │
│                          ┌─────▼──────┐                       │
│                          │ Audit      │ (always last)         │
│                          │ Officer    │                       │
│                          └─────┬──────┘                       │
│                                │                              │
│                          ┌─────▼───────────────┐              │
│                          │ Hash Chain (ADR-019)│              │
│                          └─────────────────────┘              │
└────────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────────────────────────┐
│                  EXECUTION LAYER                               │
│                                                                │
│  ToolBroker (ADR-015)   AgentRouter (ADR-023)                 │
│  OversightGate (HITL)   CopilotOrchestrator (multi-agent)     │
│  Digital Twin (ADR-025) Notification Dispatcher               │
└────────────────────────────────────────────────────────────────┘
```

### Service contract

```python
# src/core/copilot/service.py

class CopilotService:
    """
    Single entry point voor alle Co-Pilot interacties.
    Bouwt Proposals, consulteert Council, voert uit na goedkeuring.
    """

    def __init__(
        self,
        council: AgentCouncil,
        llm_handler: LLMHandler,
        proposal_builder: ProposalBuilder,
        hitl_repo: IHITLRepository | None = None,
        tool_broker: IToolBroker | None = None,
        twin_service: ITwinService | None = None,
    ) -> None: ...

    async def handle_turn(
        self,
        tenant_id: int,
        user_id: int,
        message: str,
        context: dict[str, Any],
        stream: bool = False,
        language: str = "nl",
    ) -> CopilotTurnResponse:
        """One-shot interactie (Cmd+K, focus-builder)."""

    async def handle_chat_message(
        self,
        session_id: UUID,
        tenant_id: int,
        user_id: int,
        message: str,
    ) -> AsyncIterator[CopilotChunk]:
        """Multi-turn streaming chat (sidebar)."""

    async def submit_proactive_proposal(
        self,
        proposal: Proposal,
    ) -> CouncilDecision:
        """Proactieve monitor heeft iets opgemerkt — door de Council."""

    async def respond_to_signal(
        self,
        signal_id: UUID,
        user_response: SignalResponse,
        tenant_id: int,
        user_id: int,
    ) -> CopilotResponse:
        """Gebruiker reageert op een proactief signaal."""

    async def explain_decision(
        self,
        decision_id: UUID,
        tenant_id: int,
        user_id: int,
    ) -> DecisionExplanation:
        """Right-to-explanation API (GDPR art. 13-15)."""
```

---

## 5. De Council in detail — de zeven Officers

Elke Officer implementeert dezelfde abstracte interface, zodat de Coordinator ze uniform kan aansturen.

### 5.1 Officer base class

```python
# src/core/copilot/council/members/base.py

class Officer(ABC):
    """Abstract base class voor alle Council-leden."""

    name: ClassVar[str]
    allowed_verdicts: ClassVar[frozenset[VerdictType]]
    timeout_ms: ClassVar[int] = 500  # Per-Officer SLA

    @abstractmethod
    async def deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        """
        Beoordeel het voorstel. Moet binnen timeout_ms terugkomen.
        Bij timeout: Coordinator interpreteert als VETO (fail-secure).
        """
        ...

    @abstractmethod
    def can_cache(self, proposal: Proposal) -> bool:
        """Geeft aan of dit verdict voor 60s cachebaar is."""
        ...
```

### 5.2 Per Officer — verantwoordelijkheid en checks

#### 5.2.1 ComplianceOfficer

**Verantwoordelijkheid:** EU AI Act art. 12/13/50, GDPR, ISO 42001 compliance.

**Checks:**
- Is de proposal-actie geclassificeerd onder AI Act high-risk? (zo ja: extra logging vereist)
- Bevat de data_classification voldoende metadata voor art. 12 logging?
- Komt het Officer zelf in `ai_act_classifier.py` aan een verboden practice toe? (bv. social scoring → VETO)
- Is de gebruiker geïnformeerd dat hij met AI praat? (art. 50)

**Verdict map:**
- `APPROVE` — geen compliance bezwaren
- `APPROVE_WITH_MODIFICATION` — actie toegestaan mits aanvullende transparantie-tekst
- `VETO` — verboden practice of ontbrekende verplichte velden

**Cache:** 60s op `(action_type, data_classification)` tupel.

**Wraps:** `compliance_guardian.py` + `ai_act_classifier.py`.

#### 5.2.2 PrivacyOfficer

**Verantwoordelijkheid:** Persoonsgegevens, GDPR, consent.

**Checks:**
- Bevat `action_params` PII? (regex + ML-classifier in `gdpr_enforcer.py`)
- Heeft de gebruiker consent gegeven voor cross-session memory (ADR-026)?
- Wordt er data over tenant-grenzen heen geprobeerd? (ADR-003 — VETO)
- Bij data-export: heeft de gebruiker DSAR-rechten geactiveerd?

**Verdict map:**
- `APPROVE` — geen privacy issues
- `REQUIRE_HITL` — gebruiker moet expliciet bevestigen (bv. bulk-export)
- `VETO` — cross-tenant attempt, ontbrekend consent voor required field

**Cache:** Niet cachebaar (consent kan elk moment ingetrokken worden).

**Wraps:** `gdpr_enforcer.py` + `cookie_consent.py` + `PracticalTwinService.consent_gate`.

#### 5.2.3 SecurityOfficer

**Verantwoordelijkheid:** Tool-misbruik, prompt injection, scope-validatie.

**Checks:**
- Is `action_type` in de ToolBroker allowlist voor deze user/tenant? (ADR-015)
- Bevat `proposal.reasoning` of `action_params` patronen die op prompt injection wijzen? (PromptGuard, ADR-015 P0-6)
- Heeft de gebruiker de juiste scopes? (RBAC check)
- Wordt er een high-risk tool aangeroepen (DELETE, ADMIN)? → REQUIRE_HITL

**Verdict map:**
- `APPROVE` — alle checks slagen
- `REQUIRE_HITL` — high-risk tool gedetecteerd
- `VETO` — tool niet in allowlist, prompt injection gedetecteerd, of scope ontbreekt

**Cache:** 60s op `(action_type, user_role)` — invalidate bij scope wijziging.

**Wraps:** `tool_broker` (ADR-015) + `PromptGuard` + `RBACChecker`.

#### 5.2.4 RiskOfficer

**Verantwoordelijkheid:** Impact-classificatie, HITL escalatie, Shadow CEO veto.

**Checks:**
- Wat is de Shadow CEO risk score voor deze actie? (ADR-016)
- Raakt de actie financiën, governance, of irreversibele wijzigingen?
- Heeft de gebruiker eerder soortgelijke acties veilig uitgevoerd? (track record uit `risk_register.py`)
- Past de actie binnen de tenant-policy thresholds?

**Verdict map:**
- `APPROVE` — risico laag of medium met track record
- `REQUIRE_HITL` — risico hoog of nieuwe actor
- `VETO` — alleen bij Shadow CEO CRITICAL (zeldzaam)

**Cache:** Niet cachebaar (context-afhankelijk).

**Wraps:** `risk_register.py` + `ShadowCEOAgent`.

#### 5.2.5 EthicsOfficer (NIEUW)

**Verantwoordelijkheid:** Bias-detectie, fairness, transparantieplicht.

**Checks:**
- Bevat de Co-Pilot reasoning bias-indicatoren? (bv. demografische assumpties)
- Wordt er een suggestie gedaan die een groep gebruikers kan benadelen?
- Is de uitleg voor de gebruiker begrijpelijk in zijn taal? (i18n check)
- Vereist de actie een expliciete "ik weet dat dit AI is" disclosure?

**Verdict map:**
- `APPROVE` — ethisch geen bezwaar
- `APPROVE_WITH_MODIFICATION` — reformulering nodig (bv. neutraler taalgebruik)
- Geen VETO mogelijkheid — Ethics waarschuwt en past aan, blokkeert niet.

**Cache:** 5 min op `(message_pattern, language)` — taal en patroon zijn stabiel.

**Implementatie:** **NIEUW** — bouwt op `ethics_gate.py` skeleton met bias-detectie via curated lexicons + optionele LLM-classifier.

#### 5.2.6 ResourceOfficer (NIEUW)

**Verantwoordelijkheid:** Token-budget, rate limits, notificatie-budget, kosten.

**Checks:**
- Heeft de tenant nog token-budget voor deze actie? (Prana Economy, ADR-021)
- Past de actie binnen rate limits per user/tenant?
- Bij proactieve melding: heeft de gebruiker nog ruimte in zijn dagelijkse 25-budget?
- Is de queue depth acceptabel? Niet bij overload.

**Verdict map:**
- `APPROVE` — alle budgets ok
- `REQUIRE_DEFERRAL` — budget op, herproberen later (bij notificatie: morgen)
- Geen VETO — schaarste is geen verbod.

**Cache:** 10s op `(tenant_id, user_id, action_type)` — rate limits veranderen snel.

**Implementatie:** **NIEUW** — wraps `rate_limiter.py` + Prana token meter + nieuwe `NotificationBudgetTracker`.

#### 5.2.7 AuditOfficer (altijd laatste)

**Verantwoordelijkheid:** Tamper-evident logging conform AI Act art. 12.

**Geen verdict op het voorstel zelf** — maar:
- Bouwt het volledige `CouncilDecision` record op
- Berekent SHA-256 chained hash met vorige decision per tenant
- Schrijft naar `governance_audit_log` tabel
- Bij schrijffout: blokkeert executie (fail-secure)
- Genereert `explanation_for_user` veld voor right-to-explanation

**Verdict map:**
- `APPROVE` — log geschreven, hash chain intact
- `VETO` (zeldzaam) — audit write faalde of hash chain broken

**Cache:** Niet cachebaar — elke decision is uniek.

**Wraps:** `hash_chain.py` + `governance/audit.py` + nieuw schema-veld voor AI Act metadata.

### 5.3 De Coordinator

```python
# src/core/copilot/council/coordinator.py

class AgentCouncil:
    """
    Coördineert de beraadslaging van zeven Officers en aggregeert
    hun verdicts tot één CouncilDecision.
    """

    def __init__(
        self,
        compliance: ComplianceOfficer,
        privacy: PrivacyOfficer,
        security: SecurityOfficer,
        risk: RiskOfficer,
        ethics: EthicsOfficer,
        resource: ResourceOfficer,
        audit: AuditOfficer,
        circuit_breakers: CircuitBreakerRegistry,
    ) -> None: ...

    async def deliberate(self, proposal: Proposal) -> CouncilDecision:
        """
        Stappen:
        1. Parallel verdict gathering (asyncio.gather met per-Officer timeout)
        2. Detecteer veto's → BLOCKED
        3. Detecteer HITL eisen → HITL_REQUIRED
        4. Detecteer defer eisen → DEFERRED
        5. Detecteer modifications → MODIFIED + return aan service voor retry
        6. Anders → APPROVED
        7. AuditOfficer schrijft uiteindelijke beslissing naar hash chain
        8. Return CouncilDecision
        """

    async def _gather_verdicts(
        self, proposal: Proposal, context: DeliberationContext
    ) -> list[OfficerVerdict]:
        """Parallel beraadslaging met fail-secure timeout."""
```

---

## 6. Beslissingsflow van begin tot eind

### Scenario: gebruiker typt in Cmd+K "exporteer alle klantgegevens"

```
TIJDLIJN

t=0ms     User typt "exporteer alle klantgegevens" → Cmd+K submit
t=5ms     Frontend POST /api/v1/copilot/turn met JWT
t=10ms    CopilotService extraheert tenant_id, user_id uit JWT
t=12ms    Rate limit check (ResourceOfficer pre-check) — OK
t=15ms    CopilotService roept LLM aan voor intent + JSON contract output
t=850ms   LLM antwoordt: action="export_data", scope="all_customers"
t=855ms   CopilotService bouwt Proposal:
            - action_type="export_data"
            - action_params={scope:"all_customers"}
            - data_classification=RESTRICTED (PII bulk)
            - confidence=0.92
            - reasoning="User asked for bulk customer export..."
t=860ms   Proposal naar AgentCouncil.deliberate()
t=860ms   PARALLEL:
            - ComplianceOfficer: APPROVE (legitiem business need)
            - PrivacyOfficer: REQUIRE_HITL (bulk PII, DSAR-flow)
            - SecurityOfficer: REQUIRE_HITL (export tool = high-risk)
            - RiskOfficer: REQUIRE_HITL (Shadow CEO score = HIGH)
            - EthicsOfficer: APPROVE_WITH_MODIFICATION (voeg waarschuwing toe)
            - ResourceOfficer: APPROVE (budget ok)
t=910ms   AuditOfficer schrijft beraadslaging naar hash chain
t=915ms   Coordinator aggregeert:
            - geen VETO
            - REQUIRE_HITL gevonden → eindverdict = HITL_REQUIRED
t=920ms   CouncilDecision:
            - verdict = HITL_REQUIRED
            - hitl_request_id = UUID
            - explanation_for_user = "Deze actie raakt persoonsgegevens
              en vereist expliciete toestemming."
t=925ms   CopilotService persisteert HITL request via OversightGate
t=930ms   Notification dispatched naar user UI:
            "De Co-Pilot wil iets uitvoeren dat jouw goedkeuring vereist."
t=935ms   Frontend toont MissionProposalModal met:
            - Wat de Co-Pilot wil doen
            - Wie heeft er meegekeken (de zeven Officers + verdicts)
            - Knoppen: Goedkeuren / Aanpassen / Weigeren
            - Link "Waarom raadde ik dit aan?" naar AuditViewer
t=...      Gebruiker beslist → bevestiging via /oversight-gate/approve
```

### Sequence diagram (vereenvoudigd)

```
User      Frontend    CopilotSvc    LLM       Council     Officers    AuditOfc    HashChain    OversightGate
 │          │            │           │           │           │           │            │              │
 │ Cmd+K    │            │           │           │           │           │            │              │
 ├─────────►│            │           │           │           │           │            │              │
 │          │ POST turn  │           │           │           │           │            │              │
 │          ├───────────►│           │           │           │           │            │              │
 │          │            │ NLU       │           │           │           │            │              │
 │          │            ├──────────►│           │           │           │            │              │
 │          │            │◄──────────┤           │           │           │            │              │
 │          │            │ proposal  │           │           │           │            │              │
 │          │            ├───────────────────────►│           │           │            │              │
 │          │            │           │           │ parallel  │           │            │              │
 │          │            │           │           ├──────────►│           │            │              │
 │          │            │           │           │◄──────────┤ verdicts  │            │              │
 │          │            │           │           │ aggregate │           │            │              │
 │          │            │           │           ├───────────────────────►│            │              │
 │          │            │           │           │           │           │ write log  │              │
 │          │            │           │           │           │           ├───────────►│              │
 │          │            │           │           │           │           │◄───────────┤              │
 │          │            │           │           │ decision  │           │            │              │
 │          │            │◄──────────────────────┤           │           │            │              │
 │          │            │ HITL req  │           │           │           │            │              │
 │          │            ├───────────────────────────────────────────────────────────────────────────►│
 │          │ modal      │           │           │           │           │            │              │
 │          │◄───────────┤           │           │           │           │            │              │
 │ approve  │            │           │           │           │           │            │              │
 ├─────────►│            │           │           │           │           │            │              │
```

---

## 7. Audit, hash chain en bewaartermijnen

### 7.1 Hash chain structuur

Per tenant wordt één doorlopende keten bijgehouden. Elke `CouncilDecision` hash is SHA-256 over een gecanoniceerde JSON van:

```python
{
    "decision_id": "uuid",
    "proposal_id": "uuid",
    "tenant_id": 42,
    "user_id": 1337,
    "timestamp": "2026-05-22T14:23:45.123456+00:00",
    "verdict": "HITL_REQUIRED",
    "action_type": "export_data",
    "action_params_hash": "sha256(...)",
    "data_classification": "RESTRICTED",
    "model_id": "deepseek-chat-v3.1",
    "model_version": "2026-05-15",
    "reasoning_hash": "sha256(reasoning_text)",
    "officer_verdicts_hash": "sha256(merkle_root_of_7_verdicts)",
    "previous_hash": "sha256(...) | 'genesis'"
}
```

### 7.2 Wat wordt er per Officer-uitspraak opgeslagen?

```python
@dataclass(frozen=True)
class OfficerVerdict:
    officer_name: str               # "PrivacyOfficer"
    verdict: VerdictType            # REQUIRE_HITL
    reason_code: str                # "BULK_PII_EXPORT"
    reason_text: str                # Natuurlijke taal uitleg
    evidence: dict[str, Any]        # Bewijsstukken voor audit
    deliberation_ms: int            # Per-Officer latentie
    confidence: float               # Officer's eigen confidence
    used_cache: bool                # Was dit een gecachet verdict?
    officer_version: str            # Voor reproduceerbaarheid
```

### 7.3 Tabel-schema (nieuwe Alembic migratie)

```sql
CREATE TABLE council_decisions (
    decision_id UUID PRIMARY KEY,
    proposal_id UUID NOT NULL,
    tenant_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verdict VARCHAR(32) NOT NULL,
    action_type VARCHAR(128) NOT NULL,
    action_params JSONB NOT NULL,
    data_classification VARCHAR(16) NOT NULL,
    model_id VARCHAR(64) NOT NULL,
    model_version VARCHAR(32) NOT NULL,
    reasoning TEXT NOT NULL,
    explanation_for_user TEXT NOT NULL,
    deliberation_ms INTEGER NOT NULL,
    hitl_request_id UUID,
    modifications JSONB,
    decision_hash VARCHAR(64) NOT NULL,
    previous_decision_hash VARCHAR(64),
    CONSTRAINT fk_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE INDEX idx_council_tenant_time ON council_decisions (tenant_id, timestamp);
CREATE INDEX idx_council_user_time ON council_decisions (tenant_id, user_id, timestamp);
CREATE INDEX idx_council_verdict ON council_decisions (tenant_id, verdict);
-- RLS policy per ADR-005
ALTER TABLE council_decisions ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON council_decisions
    USING (tenant_id = current_setting('app.current_tenant')::integer);

CREATE TABLE officer_verdicts (
    verdict_id UUID PRIMARY KEY,
    decision_id UUID NOT NULL REFERENCES council_decisions(decision_id) ON DELETE CASCADE,
    tenant_id INTEGER NOT NULL,
    officer_name VARCHAR(32) NOT NULL,
    verdict VARCHAR(32) NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    reason_text TEXT NOT NULL,
    evidence JSONB NOT NULL,
    deliberation_ms INTEGER NOT NULL,
    confidence NUMERIC(4,3) NOT NULL,
    used_cache BOOLEAN NOT NULL DEFAULT FALSE,
    officer_version VARCHAR(32) NOT NULL
);

CREATE INDEX idx_verdicts_decision ON officer_verdicts (decision_id);
ALTER TABLE officer_verdicts ENABLE ROW LEVEL SECURITY;
```

### 7.4 Retentie en cleanup

| Tabel | Bewaartermijn | Cleanup actor |
|-------|---------------|---------------|
| `council_decisions` | 13 maanden | `cleanup_council_decisions` Dramatiq actor, dagelijks 03:00 |
| `officer_verdicts` | 13 maanden (cascade) | Cascade via FK |
| `notification_dispatch_log` | 90 dagen | `cleanup_notification_log`, dagelijks 03:15 |
| `user_notification_preferences` | Tot DSAR / accountverwijdering | Manual via DSAR-flow |

De cleanup-actors bouwen voort op `retention_cleanup.py` en gebruiken `TenantFilterBypass` voor cross-tenant uitvoering (zoals ADR-007 P0-8 patroon).

### 7.5 Right-to-explanation API

```
GET /api/v1/copilot/audit/{decision_id}
Auth: JWT vereist
Tenant-scope: gebruiker mag alleen eigen tenant decisions zien
RBAC: tenant-admin mag alle eigen tenant decisions zien

Response 200:
{
  "decision_id": "uuid",
  "verdict": "HITL_REQUIRED",
  "timestamp": "2026-05-22T14:23:45+00:00",
  "action_summary": "Exporteren van persoonsgegevens van 1247 klanten",
  "explanation": "Deze actie raakt persoonsgegevens en vereist...",
  "officer_summaries": [
    {"officer": "ComplianceOfficer", "verdict": "approve", "summary": "..."},
    {"officer": "PrivacyOfficer", "verdict": "require_hitl", "summary": "..."},
    ...
  ],
  "user_rights": {
    "can_contest": true,
    "contest_url": "/api/v1/copilot/audit/{decision_id}/contest",
    "data_protection_officer_email": "dpo@..."
  },
  "hash_chain_proof": {
    "decision_hash": "...",
    "previous_hash": "...",
    "verification_endpoint": "/api/v1/copilot/audit/verify"
  }
}
```

---

## 8. Proactieve patronen — Fase 1

Twee patroongroepen voor de eerste sprint:

### 8.1 Platform-bewaking (systeemmetrics, geen gebruikersdata)

> **Implementatie:** `src/core/copilot/proactive/monitors/` — Sprint 5 dag 2 (2026-05-24)

| Trigger | Detectie | Voorbeeld melding | Bestand |
|---------|----------|-------------------|---------|
| Falende agent | `AgentHealthMonitor` rapporteert >50% failure rate in laatste 50 calls | "Agent `donor-router` faalt 27x in het laatste uur — wil je zien?" | `monitors/agent_health.py` |
| Trage workflow | P95 latency >3x baseline gedurende 10 min | "Workflow `monthly-report` is vandaag 4x langzamer dan normaal — kijken?" | `monitors/workflow_latency.py` |
| Queue depth alert | Dramatiq queue >1000 jobs of >5 min wait | "Er staan 1247 jobs te wachten in `default` queue — schalen?" | `monitors/queue_depth.py` |
| Token-piek | LLM token usage >2x dagelijks gemiddelde | "Tenant verbruikte vandaag 4.2M tokens (gemiddeld 1.8M) — review?" | `monitors/token_spike.py` |
| Circuit breaker geopend | `FailoverLLMProvider` markeerde provider als down | "DeepSeek is 5 min onbereikbaar — failover naar Anthropic actief." | `monitors/circuit_breaker.py` |

### 8.2 Compliance- en veiligheidssignalen (raakt gebruikersactie)

| Trigger | Detectie | Voorbeeld melding |
|---------|----------|-------------------|
| PII export op handen | User klikt "Export" op een tabel met PII-kolommen | "Je staat op het punt persoonsgegevens te exporteren — controle vereist." |
| Workflow raakt gevoelige data | Workflow-config bevat PII fields | "Deze workflow raakt persoonsgegevens — DPIA-template invullen?" |
| Inconsistente rollen | 3+ gebruikers in tenant kregen vanmiddag permission-denied | "Er kan iets mis zijn met rollen — wil je de RBAC-config zien?" |
| Verlopen consent | Consent voor cross-session memory verloopt over 7 dagen | "Je consent loopt af op 29 mei — vernieuwen?" |

### 8.3 Architectuur van een proactieve monitor

```python
# src/core/copilot/proactive/monitor.py

class ProactiveMonitor(ABC):
    """Base class voor alle proactieve monitoren."""

    name: ClassVar[str] = ""
    version: ClassVar[str] = "1.0.0"
    interval_seconds: ClassVar[int] = 300  # 0 = event-driven
    default_severity: ClassVar[Severity] = Severity.LOW
    default_classification: ClassVar[DataClassification] = DataClassification.INTERNAL

    def __init__(self, copilot_service: Any, dispatcher: Any) -> None:
        self._copilot_service = copilot_service
        self._dispatcher = dispatcher

    @abstractmethod
    async def detect(self, tenant_id: int) -> list[Signal]:
        """Run detectie voor één tenant; retour: gedetecteerde signalen."""

    async def propose_to_council(self, signal: Signal) -> CouncilDecision:
        """Bouw Proposal en submit naar Council."""
        proposal = Proposal(
            tenant_id=signal.tenant_id,
            user_id=signal.affected_user_id,
            trigger=ProposalTrigger.PROACTIVE_MONITOR,
            action_type="send_notification",
            action_params={
                "signal_id": str(signal.signal_id),
                "title": signal.title,
                "body": signal.body,
                "severity": signal.severity.value,
                "actions": signal.suggested_actions,
            },
            reasoning=signal.detection_reasoning,
            data_classification=signal.data_classification,
            confidence=signal.confidence,
            model_id=f"proactive-monitor:{self.name}",
            model_version=self.version,
            context_snapshot=signal.context,
        )
        decision = await self._copilot_service.submit_proactive_proposal(proposal)
        if decision.verdict == DecisionVerdict.APPROVED:
            await self._dispatcher.dispatch(signal, decision)
        return decision
```

### 8.4 Scheduler

Monitoren worden gescheduled via APScheduler (al aanwezig per ADR-006 ecosystem):

```python
# src/core/copilot/proactive/scheduler.py

class ProactiveScheduler:
    """Plant en runt monitoren per tenant."""

    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        tenant_repo: Any,
        monitors: list[ProactiveMonitor],
    ) -> None:
        ...

    def start(self) -> None:
        """Registreer elke monitor als APScheduler job en start de scheduler."""

    def shutdown(self, wait: bool = True) -> None:
        """Stop de scheduler."""

    async def _run_for_all_tenants(self, monitor: ProactiveMonitor) -> None:
        """Voor elke tenant: monitor.detect() → propose_to_council().

        - Sequentieel per tenant (geen DB-pool uitputting)
        - asyncio.wait_for timeout = interval_seconds * 0.8
        - Per-tenant try/except zodat één crash de rest niet blokkeert
        - Event-driven monitors (interval_seconds <= 0) worden overgeslagen
        """
```

---

## 9. Notificatie UX en het 25-budget

### 9.1 Het budget-mechanisme

De ResourceOfficer telt per gebruiker per kalenderdag (UTC) het aantal afgegeven notificaties. Bij signaalvoorstellen 1-25 → `APPROVE` mits andere checks slagen. Bij voorstellen 26+ → `REQUIRE_DEFERRAL` (verschijnt morgen of in dagelijkse samenvatting), uitgezonderd `severity=CRITICAL`.

```python
# src/core/copilot/notification/budget.py

class NotificationBudgetTracker:
    DEFAULT_DAILY_LIMIT = 25
    MIN_LIMIT = 0
    MAX_LIMIT = 100

    async def consume(
        self,
        tenant_id: int,
        user_id: int,
        severity: Severity,
    ) -> BudgetVerdict:
        """
        Returns:
            BudgetVerdict.APPROVED   — binnen budget
            BudgetVerdict.DEFERRED   — buiten budget, verschuif naar samenvatting
            BudgetVerdict.OVERRIDE   — CRITICAL severity, altijd door
        """

    async def get_user_preference(self, user_id: int) -> NotificationPreference:
        """Haal user-instelling op (custom limit + batching mode)."""
```

### 9.2 Drie signaal-lagen

| Laag | UI | Wanneer |
|------|-----|---------|
| **Stil teken** (passief) | Gekleurde dot op het Co-Pilot icoon | Standaard voor elk signaal |
| **Inline kaart** (semi-actief) | Toast/card op de huidige pagina | Wanneer signaal relevant is voor huidige route |
| **Pop-up modal** (actief) | Onderbreekt de gebruiker | Alleen voor severity=CRITICAL (bv. data breach) |

### 9.3 Smart batching

Gebruikers kunnen kiezen tussen drie modes:

- **Individueel** (default): elk signaal als eigen notificatie, max 25/dag
- **Dagelijkse samenvatting**: één digest om 09:00 met alle signalen van de afgelopen 24u
- **Hybride**: critical signalen direct, rest in dagelijkse samenvatting

### 9.4 Settings UI

```
┌─────────────────────────────────────────────────────────┐
│  Co-Pilot notificatie-instellingen                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Hoeveel meldingen per dag wil je maximaal ontvangen?  │
│  [────────●─────────] 25                                │
│  0                                              100     │
│                                                         │
│  Bezorging:                                            │
│  ○ Direct (zodra ze opkomen)                           │
│  ● Direct + dagelijkse samenvatting om 09:00           │
│  ○ Alleen dagelijkse samenvatting (rustigste optie)    │
│                                                         │
│  Kritieke meldingen altijd direct: [✓]                 │
│                                                         │
│  [Opslaan]                                             │
└─────────────────────────────────────────────────────────┘
```

---

## 10. Integratie met bestaande componenten

### 10.1 ToolBroker (ADR-015)

Na `APPROVED` of `MODIFIED` verdict roept `CopilotService.execute_after_approval()` de ToolBroker aan. ToolBroker verifieert dubbelop (allowlist, scopes) en voert uit. Sandboxing en logging blijven via ToolBroker — Council voegt **governance**-laag toe, geen **execution**-laag.

### 10.2 AgentRouter (ADR-023)

Wanneer Co-Pilot besluit `action_type="route_to_specialist"`, roept hij na Council-goedkeuring de AgentRouter aan met `task_description` en `tenant_id`. AgentRouter doet zijn 5-tier routing (cache→cache→capability→LLM→fallback). Council is `pre`-routing; AgentRouter is `routing`.

### 10.3 Digital Twin (ADR-025, ADR-026)

PracticalTwinService levert:
- **User profile snapshot** voor `Proposal.context_snapshot` (alleen met consent)
- **Pattern detection** voor proactieve "elke maandag…" suggestions
- **Consent gate** wordt geconsulteerd door PrivacyOfficer

### 10.4 OversightGate (ADR-017)

Bij `HITL_REQUIRED` persisteert CopilotService een `HITLRequest` via OversightGate. Frontend krijgt notificatie, toont MissionProposalModal, en bij goedkeuring stuurt POST naar OversightGate, die Council-decision opnieuw evalueert met `human_approval=True` flag — andere Officers kunnen alsnog vetoen (zeldzaam).

### 10.5 CopilotOrchestrator (bestaand)

De huidige `src/core/orchestrator/copilot_orchestrator.py` wordt opgenomen in `CopilotService.execute_multi_agent_workflow()` voor goedgekeurde multi-agent taken. De wave-based parallelisatie van bestaande implementatie blijft intact.

---

## 11. API surface en frontend touchpoints

### 11.1 Geconsolideerde REST/WS endpoints

| Methode | Pad | Doel | Auth |
|---------|-----|------|------|
| POST | `/api/v1/copilot/turn` | One-shot interactie (Cmd+K, focus-builder) | JWT verplicht |
| WS | `/ws/copilot/chat` | Multi-turn streaming chat | JWT verplicht (cookie + query fallback) |
| POST | `/api/v1/copilot/proactive/{signal_id}/respond` | Reageer op proactief signaal | JWT verplicht |
| GET | `/api/v1/copilot/audit/{decision_id}` | Right-to-explanation | JWT verplicht |
| POST | `/api/v1/copilot/audit/{decision_id}/contest` | Beslissing aanvechten (GDPR art. 22) | JWT verplicht |
| GET | `/api/v1/copilot/notifications/preferences` | Lees notificatie-voorkeur | JWT verplicht |
| PUT | `/api/v1/copilot/notifications/preferences` | Wijzig notificatie-voorkeur | JWT verplicht |
| GET | `/api/v1/copilot/audit/verify` | Verifieer hash chain integriteit | tenant-admin |
| GET | `/api/v1/copilot/audit/report?from=...&to=...&format=pdf` | Audit-rapport genereren | tenant-admin |

**Te depreceren** (na fase 4):
- `POST /api/v1/intents/parse` → folded in `/api/v1/copilot/turn`
- `POST /api/v1/ai-copilot/suggest-tools` → folded in `/api/v1/copilot/turn`

### 11.2 JSON contract (Co-Pilot output)

```json
{
  "decision_id": "uuid",
  "verdict": "APPROVED|MODIFIED|HITL_REQUIRED|DEFERRED|BLOCKED",
  "message": "Natuurlijke-taal antwoord in gebruikerstaal",
  "action": "navigate_to|execute_workflow|send_notification|null",
  "action_params": {},
  "confidence": 0.92,
  "council_summary": {
    "approve": 5,
    "modify": 0,
    "require_hitl": 2,
    "defer": 0,
    "veto": 0
  },
  "explanation_url": "/api/v1/copilot/audit/{decision_id}",
  "hitl_request_id": "uuid|null"
}
```

### 11.3 Frontend touchpoints

#### Behouden en uitbreiden:
- `CommandPalette.tsx` — fix `apiEndpoint`, voeg auth-header, vervang mock-mission door echte API-call
- `AICopilotPanel.tsx` — refactor naar één WS-protocol; voeg signaal-indicator toe
- `MissionProposalModal.tsx` — toon nu de Council-uitslag per Officer; vervang mock met echte `/api/v1/copilot/audit/{decision_id}` call
- `focus-builder/AICopilot.tsx` — fix inline styles, vervang `alert()` met Toast, voeg auth toe

#### Nieuw te bouwen:
- `CouncilSignal.tsx` — persistente AI-aanwezigheid indicator (links onderin scherm)
- `ProactiveSignalToast.tsx` — inline kaart voor niveau 2 meldingen
- `AuditViewer.tsx` — toon `CouncilDecision` met alle Officer-uitspraken, hash chain proof, contestatie-knop
- `NotificationSettings.tsx` — instelling 25-budget + batching mode
- `useCouncilDecision.ts` — hook voor right-to-explanation API
- `useNotificationBudget.ts` — hook voor lopend dagelijks aantal
- `useProactiveSignals.ts` — hook voor inkomende signalen via WS-subscribe

### 11.4 EU AI Act art. 50 — AI-aanwezigheid indicator

Op élke pagina met Co-Pilot-functionaliteit (= alle pagina's) staat:
- Klein icoon links onderin: pulserend bolletje + "AI-assistent actief"
- Tooltip on hover: "Je interactie met deze applicatie wordt ondersteund door AI. Klik voor uitleg."
- Klik opent een drawer met: korte uitleg, link naar AuditViewer, link naar privacy-statement

---

## 12. Testen, observability en deploy

### 12.1 Testdekking per laag

| Laag | Tests | Locatie |
|------|-------|---------|
| Officers (per officer) | ~30 unit tests/officer (happy/unhappy/edge) | `tests/unit/copilot/council/members/` |
| Coordinator | ~60 unit tests + 10 integration | `tests/unit/copilot/council/test_coordinator.py` |
| CopilotService | ~40 unit + 15 integration | `tests/unit/copilot/test_service.py` + `tests/integration/copilot/` |
| Proactive monitoren | ~20 per monitor, behavioral | `tests/unit/copilot/proactive/` |
| Notification budget | ~15 unit + 5 integration | `tests/unit/copilot/notification/test_budget.py` |
| Audit + hash chain | ~25 unit + 10 integration (cross-decision) | `tests/unit/copilot/test_audit.py` |
| Frontend componenten | per component ~10-20 vitest | `frontend/src/components/copilot/__tests__/` |
| E2E gebruikersflow | Cmd+K → Council → HITL → approval | `frontend/tests/integration/copilot-council.integration.test.tsx` |

### 12.2 Verplichte security tests

Per CLAUDE.md regel 10 (repository tenant isolation):

1. Tenant A kan geen council_decisions van tenant B inzien
2. Een verlopen JWT geeft 401 op alle copilot endpoints
3. tenant_id in request body wordt genegeerd (JWT is source of truth)
4. Hash chain blijft valid bij concurrent writes binnen één tenant
5. RLS-bypass via `current_setting('app.current_tenant')` werkt zoals verwacht

### 12.3 Behavioral tests (CLAUDE.md kwaliteitsloop stap 4)

Minstens deze:

1. "Gebruiker typt 'exporteer klanten' → ziet HITL modal met uitleg van Privacy Officer"
2. "Agent X faalt 10x → gebruiker ziet stil teken op Co-Pilot icoon"
3. "Gebruiker krijgt 25e notificatie → 26e verschijnt in dagelijkse samenvatting"
4. "Gebruiker contesteert een Council decision → admin krijgt notificatie"
5. "Tenant-admin opent AuditViewer → ziet zeven Officer-uitspraken + hash chain proof"

### 12.4 Observability (ADR-014)

Prometheus metrics:
- `copilot_turns_total{tenant, status}` counter
- `copilot_council_deliberation_seconds{officer}` histogram
- `copilot_council_verdict_total{officer, verdict}` counter
- `copilot_notifications_dispatched_total{tenant, severity}` counter
- `copilot_notifications_deferred_total{tenant, reason}` counter
- `copilot_hitl_pending` gauge (per tenant)
- `copilot_audit_writes_total{status}` counter
- `copilot_hash_chain_breaks_total` counter (moet 0 zijn)

OpenTelemetry trace spans:
- `copilot.turn` (root span)
- `copilot.council.deliberate` (child)
- `copilot.council.officer.{name}` (per officer)
- `copilot.audit.write` (child)
- `copilot.executor.{tool_name}` (child na approval)

Alerts (Grafana):
- `copilot_hash_chain_breaks_total > 0` → CRITICAL (tamper detection)
- `copilot_council_deliberation_seconds{p99} > 1s` → WARNING
- `copilot_audit_writes_total{status="failed"}` rate > 0 → CRITICAL

### 12.5 Deploy en feature-flags

Alle nieuwe code achter feature flag `copilot_council_v1`. Rollout:

1. Internal tenant alleen (tenant_id=1)
2. 10% van bestaande tenants (canary)
3. 50% (na 1 week zonder alerts)
4. 100% (na 2 weken zonder alerts)
5. Verwijder feature flag (week 8)

---

## 13. Roadmap (Fase 2+)

Wat **niet** in fase 1 zit maar wel ontworpen is voor uitbreiding:

| Fase | Feature | Schatting |
|------|---------|-----------|
| 2.1 | Patroonherkenning ("elke maandag dit rapport") | 2 weken |
| 2.2 | Werk wegnemen (pre-summarisatie, lege state invullen) | 3 weken |
| 2.3 | Per-tenant Council policy overrides via YAML | 2 weken |
| 2.4 | Externe auditor-export (signed PDF + JSON) | 1 week |
| 2.5 | Real-time compliance score dashboard | 2 weken |
| 3.1 | Tenant-customizable master prompt (brand voice koppeling) | 2 weken |
| 3.2 | Multi-language support uitbreiden (NL/EN/DE/FR) | 1 week |
| 3.3 | Voice interface (spraak input/output) | 4 weken |
| 4.1 | Federated Council (cross-tenant compliance learning) | 6 weken |

---

## Vastgelegde keuzes (besloten 2026-05-22)

Deze beslissingen zijn door Rakesh akkoord op 2026-05-22 en zijn vanaf nu bindend voor de implementatie:

1. **JSON mode bij LLM-calls** — JA. Alle LLM-aanroepen gebruiken structured output (JSON mode bij DeepSeek/OpenAI; tool-use met JSON schema bij Anthropic). Pydantic validatie als finale vangnet. De Co-Pilot accepteert nooit free-text LLM-antwoord voor actie-beslissingen.
2. **Officer timeouts** — Standaard 500ms voor alle Officers, met uitzonderingen: ComplianceOfficer 800ms (LLM-backed classifier), RiskOfficer 600ms (context-zware analyse), ResourceOfficer 200ms (snelle Redis-checks), AuditOfficer 400ms. Timeout → fail-secure VETO interpretation.
3. **Hash chain opslag** — Optie A: extra kolommen toevoegen aan bestaande `governance_audit_log` (backward compatible, geen aparte tabel). Plus `council_decisions` en `officer_verdicts` tabellen voor Council-specifieke metadata, gekoppeld via `decision_id`.
4. **Officer versioning** — Semver per Officer (bv. `"1.0.0"`). Versie wordt bij élke beslissing vastgelegd in het `officer_verdicts` record. Bij upgrade blijven oude beslissingen reproduceerbaar via versie-tag. Coordinator weigert te starten bij ontbrekende versie-string (fail-fast).

### Multilingual output (apart genoteerd)

Niet eerder besloten: hoe gaat de Council om met meertalige LLM-output? Voorstel: bias-checks in EthicsOfficer gebruiken per-taal lexicon (NL + EN voor MVP, DE/FR/ES post-MVP). De `explanation_for_user` wordt altijd in de taal van de gebruiker geschreven (gehaald uit JWT `language` claim of cookie).

---

*Laatst bijgewerkt: 2026-05-24. Volgende update: na Sprint 4 retrospective.*
