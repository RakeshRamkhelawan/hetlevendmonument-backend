# Focus Builder — Streaming Redesign

**Date:** 2026-03-22
**Status:** Approved
**Branch:** feature/practical-digital-twin

---

## Probleem

De Focus Builder op `/focus-builder` is gedeeltelijk gebouwd maar fundamenteel gebroken:

| Component | Status | Oorzaak |
|---|---|---|
| Flow CRUD (opslaan/laden) | Werkt | — |
| ReactFlow canvas | Werkt (basis) | — |
| AI generatie via chat | **Kapot** | `workflow_generation_endpoints.py` is nooit geregistreerd in `app_factory.py` of `router_registry.py` |
| Chat verfijning | **Kapot** | `workflow_refinement_endpoints.py` is ook nooit geregistreerd |
| `useFocusBuilderChat` hook | **Zinloos** | Beheert alleen localStorage — roept nooit een backend aan |
| `/api/v1/focus-builder/ai/generate` | **Fake** | Template-gebaseerde hardcoded if/else logica, geen LLM |

De gebruiker kan een workflow aanmaken maar kan niets verfijnen via chat, heeft geen conversatiegeheugen en krijgt geen live feedback op het canvas.

---

## Ontwerpdoelen

1. **Hybride interactiemodel** — chat genereert, canvas verfijnt visueel én via chat
2. **Gelaagde complexiteit** — laagdrempelig voor business users, dieper voor power users
3. **Socratische onboarding** — AI vraagt door tot ze genoeg context heeft om te genereren
4. **Preview-first verfijning** — geen directe wijzigingen, altijd een voorstel met Accepteer/Weiger
5. **Live streaming** — nodes verschijnen één voor één op het canvas terwijl de AI genereert
6. **Volledige executie** — workflow draait via ActivePieces, real-time status per node
7. **Learning loop** — Digital Twin onthoudt gebruikersvoorkeuren over sessies heen
8. **Mooie UI** — licht Perplexity-geïnspireerd chat panel + donker canvas

---

## Architectuur

### Eén WebSocket verbinding beheert alles

```
ws://host/api/v1/focus-builder/ws/chat
```

Geen aparte HTTP calls voor generatie of verfijning. Dezelfde socket handelt chat, generatie, verfijning én executie-status af. JWT authenticatie via cookie (patroon uit bestaande `flow_status_websocket`).

### Componenten

```
Frontend                          Backend
─────────────────────────────     ──────────────────────────────────
useFocusBuilderWS (NIEUW)    ←→   WS /focus-builder/ws/chat (NIEUW)
  ↓ writes to store                 ↓ delegates to
WorkflowBuilderStore (uitbr.)     FocusBuilderChatAgent (NIEUW)
  ↓ reads from                      ↓ wraps
FocusCanvas (uitbr.)              WorkflowGeneratorAgent (bestaand)
FocusChatPanel (NIEUW)            FocusBuilderService (bestaand)
FocusModeBuilderEnhanced (beh.)   PracticalTwinService (bestaand)
                                  UserBehaviorObserver (bestaand)
```

---

## WebSocket Protocol

### Client → Server

```jsonc
// Chat bericht (generatie of verfijning)
{ "type": "message", "content": "voeg een delay toe van 1 uur",
  "workflow_snapshot": { "nodes": [...], "edges": [...] } }

// Voorstel accepteren → ghost nodes worden permanent, opslaan
{ "type": "accept_proposal", "proposal_id": "prop_abc123" }

// Voorstel weigeren → ghost nodes verdwijnen
{ "type": "reject_proposal", "proposal_id": "prop_abc123" }

// Workflow uitvoeren
{ "type": "execute", "flow_id": 42 }

// Heartbeat
{ "type": "ping" }
```

### Server → Client

```jsonc
// Sessie gestart — client ontvangt conversation_id voor reconnect gebruik
{ "type": "session_init", "conversation_id": "conv_uuid123" }

// AI is aan het nadenken
{ "type": "thinking" }

// Streaming tekst token voor token
{ "type": "text_chunk", "content": "Ik voeg een...", "proposal_id": "prop_abc123" }

// Node voorstel — canvas toont direct een ghost node
{ "type": "node_proposed", "proposal_id": "prop_abc123",
  "node": { "id": "delay_1", "type": "delay",
             "data": { "label": "Wacht 1 uur", "duration": 3600 },
             "position": { "x": 300, "y": 150 } },
  "edges": [{ "source": "trigger_1", "target": "delay_1" }] }

// Generatie/verfijning klaar — toon Accepteer/Weiger knoppen
{ "type": "proposal_complete", "proposal_id": "prop_abc123",
  "node_count": 1, "explanation": "Delay van 1 uur toegevoegd" }

// Executie status per node (real-time)
{ "type": "exec_progress", "node_id": "slack_1",
  "status": "RUNNING" | "SUCCEEDED" | "FAILED",
  "message": "Slack bericht verzonden" }

// Heartbeat antwoord
{ "type": "pong" }
```

### Proposal lifecycle

```
server stuurt node_proposed (N keer) → canvas toont ghost nodes
server stuurt proposal_complete      → chat toont Accepteer/Weiger
gebruiker stuurt accept_proposal     → ghost nodes permanent + DB save
gebruiker stuurt reject_proposal     → ghost nodes verwijderd
```

### Conversatiegeheugen

De server bewaart per WebSocket-sessie:
- `conversation_id` (UUID)
- `message_history` (lijst van user/assistant berichten)
- `pending_proposals` (dict van proposal_id → nodes)

Bij reconnect stuurt de frontend de `conversation_id` mee. Sessie vervalt na 1 uur inactiviteit.

---

## Backend — Nieuwe Componenten

### 1. `FocusBuilderChatAgent`

**Locatie:** `src/core/agents/focus_builder_chat_agent.py`

**Verantwoordelijkheden:**
- Beheert converstatietoestand (history, pending proposals)
- Laadt Digital Twin profiel via `PracticalTwinService` vóór elke generatie
- Injecteert gebruikersvoorkeuren in de LLM systeemprompt
- Roept `WorkflowGeneratorAgent.generate_workflow()` aan met streaming callback
- Stuurt `node_proposed` events via de WebSocket callback
- Registreert accept/reject events bij `UserBehaviorObserver`

**Socratisch onboarding-flow:**
```
Sessie start → laad twin profiel → stuur begroeting
Eerste bericht → beoordeel of genoeg context is
  Onvoldoende context → stel vervolgvraag (max 3 vragen)
  Voldoende context   → start generatie met node_proposed streaming

Na 3 vragen zonder voldoende context: genereer best-effort op basis van
beschikbare informatie, met een korte toelichting dat de gebruiker de
workflow daarna verder kan verfijnen via chat.
```

**Personalisatie via twin profiel:**
```python
# Vóór generatie injecteren in system prompt:
preferred_integrations: ["slack", "webhook"]
always_adds: ["error_handler"]
preferred_complexity: "medium"
language: "nl"
past_workflow_patterns: ["dagelijkse rapporten", "notificaties bij events"]
```

### 2. WebSocket endpoint `ws/chat`

**Locatie:** `src/core/api/v1/focus_builder/router.py` (toegevoegd endpoint)

**Authenticatie:** JWT via cookie `access_token` (zelfde patroon als `flow_status_websocket`)

**Berichtdispatch:**
```python
match message["type"]:
    case "message"          → agent.handle_message(...)
    case "accept_proposal"  → agent.accept(proposal_id) + service.save(flow)
    case "reject_proposal"  → agent.reject(proposal_id)
    case "execute"          → service.execute_flow(flow_id) + stream status
    case "ping"             → websocket.send_json({"type": "pong"})
```

### Bestaande componenten — minimale aanpassingen

| Component | Aanpassing |
|---|---|
| `WorkflowGeneratorAgent` | `stream_callback` uitbreiden: stuurt ook `node_proposed` events (naast bestaande streaming) |
| `FocusBuilderService` | Ongewijzigd — CRUD en executie werken al |
| `PracticalTwinService` | Ongewijzigd — alleen lezen |
| `UserBehaviorObserver` | Ongewijzigd — alleen aanroepen met nieuwe event types |

---

## Frontend — Nieuwe Componenten

### 1. `useFocusBuilderWS` hook

**Locatie:** `frontend/src/hooks/useFocusBuilderWS.ts`

**Vervangt:** `useVibeGeneration` + `useWorkflowRefinement` (beide kapot)

**Interface:**
```typescript
interface UseFocusBuilderWSReturn {
  connectionStatus: 'connecting' | 'connected' | 'disconnected' | 'failed';
  sendMessage: (content: string) => void;
  acceptProposal: (proposalId: string) => void;
  rejectProposal: (proposalId: string) => void;
  executeFlow: (flowId: number) => void;
}
```

**Verantwoordelijkheden:**
- WebSocket lifecycle: connect, reconnect met exponential backoff, heartbeat (ping/pong elke 30s)
- Inkomende events dispatchen naar `WorkflowBuilderStore`:
  - `node_proposed` → `store.addGhostNode(node, proposalId)`
  - `proposal_complete` → `store.setProposalReady(proposalId)`
  - `exec_progress` → `store.setNodeExecStatus(nodeId, status)`
  - `text_chunk` → chat messages state
- Stuurt `conversation_id` mee bij reconnect

### 2. `FocusChatPanel` component

**Locatie:** `frontend/src/components/workflow/FocusChatPanel.tsx`

**Design:** Perplexity-geïnspireerd licht panel (wit achtergrond, subtiele shadows)

**Elementen:**
- Header met AI avatar, naam, online status
- Tabs: Bouwen / Geschiedenis / Instellingen
- Berichtenlijst:
  - `AssistantBubble` — wit kaartje met border
  - `UserBubble` — paars gevuld
  - `ThinkingIndicator` — drie paarse bouncing dots
  - `ProposalCard` — amber kaartje met node preview + Accepteer/Weiger knoppen
  - `LearningChip` — paarse chip "Onthoudt jouw voorkeuren" bij gepersonaliseerde berichten
- Suggestie chips boven input: "Node toevoegen", "Integratie", "Vereenvoudig", "Controleer"
- Input veld: groot afgerond Perplexity-stijl met mic + send knoppen
- Streaming tekst: token-voor-token rendering in laatste assistant bubble

### Uitbreidingen bestaande componenten

| Component | Uitbreiding |
|---|---|
| `WorkflowBuilderStore` | Voeg `proposals: Map<proposalId, nodes[]>` en `execStatus: Map<nodeId, status>` toe |
| `FocusCanvas` | Executie status ringen per node (groen/oranje/rood glow); accept/reject hover op ghost node zelf |
| `FocusModeBuilderEnhanced` | Vervang twee kapotte hooks door `useFocusBuilderWS`; render nieuwe `FocusChatPanel` |

---

## UI Design

### Layout

```
┌─────────────────────────────┬──────────────────────┐
│  Topbar (wit, clean)        │                      │
├─────────────────────────────┤                      │
│                             │   Chat Panel (licht) │
│   Canvas (donker)           │   400px wide         │
│   70%                       │   30%                │
│   Nodes + Ghost nodes       │   Perplexity-stijl   │
│   ReactFlow                 │   input + chips      │
│                             │                      │
└─────────────────────────────┴──────────────────────┘
```

### Kleurenschema

| Element | Kleur |
|---|---|
| Topbar achtergrond | `#ffffff` |
| Canvas achtergrond | `#050d1a` |
| Canvas grid | `rgba(255,255,255,0.025)` |
| Chat panel | `#fafafa` |
| AI bubble | `white` + `border: #e5e7eb` |
| User bubble | `#6d28d9` (paars) |
| Ghost node border | `dashed rgba(245,158,11,0.45)` (amber) |
| Ghost node bg | `rgba(245,158,11,0.05)` |
| Proposal card | `border: #fde68a`, `bg: white` |
| Accepteer knop | `#f0fdf4` / `#15803d` |
| Weiger knop | `#fef2f2` / `#dc2626` |
| Learning chip | `#faf5ff` / `#7c3aed` |

### Ghost node gedrag
- Verschijnt direct bij elk `node_proposed` event — geen wachten tot `proposal_complete`
- Zweeft met CSS animatie (`translateY 0 → -5px → 0`)
- Badge "VOORSTEL" in amber rechtsboven
- Bij hover: toon mini Accepteer/Weiger knoppen direct op de node

---

## Learning Loop

### Signalen die bijgehouden worden

| Event | Signal type | Wat het leert |
|---|---|---|
| `accept_proposal` | positief | Welke node types gebruiker accepteert |
| `reject_proposal` | negatief | Welke node types gebruiker weigert |
| Workflow opgeslagen | positief | Welke integraties (Slack, webhook, etc.) |
| Chat bericht taal | observatie | Taalvoorkeur (NL/EN/mixed) |
| Altijd toevoegen na generatie | patroon | Vaste patronen ("altijd error handler") |

### Personalisatie in de praktijk

Bij elke nieuwe generatie injecteert `FocusBuilderChatAgent` het twin profiel als context in de LLM systeemprompt:

```
Je kent deze gebruiker:
- Geeft de voorkeur aan Slack (87% van workflows)
- Voegt altijd een error_handler toe
- Praat in het Nederlands
- Bouwt voornamelijk notificatie-workflows
- Laatsbekende workflow: "Lead notificaties via Slack"

Genereer met deze voorkeuren meegenomen.
```

Bij de eerste generatie in een sessie toont de AI een `LearningChip` in het chat panel om de gebruiker te laten weten dat personalisatie actief is.

---

## Wat er NIET verandert

- `FocusBuilderService` — CRUD en ActivePieces executie logica
- `WorkflowGeneratorAgent` — Gemini LLM integratie (alleen stream_callback licht uitbreiden)
- Database schema — geen migraties nodig
- `FocusBuilderCanvas` (de oudere component) — wordt niet gebruikt door de hoofdpagina
- Auto-save logica in `useAutoSave`
- Keyboard shortcuts in `useKeyboardShortcuts`
- Bestaande routing (`/focus-builder`)

---

## Wat er verwijderd/vervangen wordt

| Oud | Vervangen door |
|---|---|
| `useVibeGeneration` (kapot) | `useFocusBuilderWS` |
| `useWorkflowRefinement` (kapot) | `useFocusBuilderWS` |
| `workflow_generation_endpoints.py` (niet geregistreerd) | Logica in `FocusBuilderChatAgent` |
| `workflow_refinement_endpoints.py` (niet geregistreerd) | Logica in `FocusBuilderChatAgent` |
| `/api/v1/focus-builder/ai/generate` (fake template logica) | WS `ws/chat` endpoint |
| `VibeChatPanel` | `FocusChatPanel` |

---

## Testplan

### Backend (pytest)
- `test_ws_chat_connect` — JWT authenticatie, tenant isolatie
- `test_ws_message_generates_nodes` — mock `WorkflowGeneratorAgent`, verwacht `node_proposed` events
- `test_ws_accept_proposal_saves_flow` — accept → flow opgeslagen in DB
- `test_ws_reject_proposal_clears_ghosts` — reject → geen DB wijziging
- `test_ws_execute_streams_status` — mock ActivePieces, verwacht `exec_progress` events
- `test_chat_agent_loads_twin_profile` — personalisatie injectie
- `test_chat_agent_observes_accept_event` — twin observer wordt aangeroepen

### Frontend (Vitest + React Testing Library)
- `useFocusBuilderWS` — mock WebSocket, test alle inkomende event types
- `FocusChatPanel` — render test, ProposalCard accept/reject interactie
- `FocusCanvas` ghost nodes — exec status ringen, hover accept/reject

### E2E (Playwright)
- Volledig scenario: open builder → AI begroet → beschrijf workflow → nodes streamen live → accepteer voorstel → run → zie status
- Verfijning scenario: bestaande workflow laden → chat bericht → preview voorstel → weiger → nieuw bericht → accepteer
- Learning scenario: tweede sessie → AI personaliseert greeting op basis van twin profiel
