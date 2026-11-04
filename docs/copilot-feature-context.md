# Co-Pilot Feature — Complete Context Document

> **DEPRECATIE-WAARSCHUWING:** Dit document beschrijft de **pre-Council audit baseline**
> (2026-05-22). Sindsdien is de volledige Agent Council architectuur (ADR-027)
> geimplementeerd. De oude versnipperde endpoints (`/api/v1/intents/parse`,
> `/api/v1/ai-copilot/suggest-tools`, `/ws/copilot/chat`) zijn in afbouw.
> Voor de huidige architectuur: zie `docs/copilot-architecture.md` en
> `docs/adr/027-copilot-agent-council.md`.

**Doel van dit document:** Volledige technische context voor een externe LLM om de Co-Pilot feature te begrijpen, de huidige staat te beoordelen, en concrete implementatieplannen op te stellen om het naar productiekwaliteit te brengen.

**Project:** SanskritiSetu — Enterprise AI Agent Operating System (multi-tenant SaaS)  
**Stack:** FastAPI + SQLAlchemy (backend), React + TypeScript + Radix UI + Tailwind (frontend), DeepSeek/multi-LLM, Redis, PostgreSQL, Dramatiq, WebSockets  
**Datum audit:** 2026-05-22  
**Auteur:** Gegenereerd via codebase-audit

---

## 1. Wat IS de Co-Pilot

De Co-Pilot is een inline AI-assistent die gebruikers helpt bij het bedienen van het SanskritiSetu platform via natuurlijke taal. Het idee: een gebruiker typt een vraag of instructie ("maak een workflow voor donor-churn"), en de Copilot:

1. Parseert de intentie (NLU)
2. Stelt een missieplan voor
3. Laat de gebruiker het plan goedkeuren (HITL)
4. Stuurt de uitvoering naar de juiste agent

De Copilot is een **orchestrator en UX-laag** — hij voert zelf geen mutaties uit, maar stuurt backend-tools aan via geautoriseerde API-calls.

### Toegangspunten

| Interface | URL | Beschrijving |
|-----------|-----|-------------|
| Command Palette | `Cmd+K` (global) | Overlay met NLU input, suggesties, missiegoedkeuring |
| AI Copilot Panel | Sidebar rechts | Real-time streaming chat via WebSocket |
| Focus Builder Copilot | In-page widget | Specifiek voor workflow-generatie |
| Mission Proposal Modal | 3-staps modal | Doel → Plan → Bevestiging flow |

---

## 2. Architectuuroverzicht (huidige staat)

```
FRONTEND
  CommandPalette.tsx          ← Cmd+K overlay, NLU + missiegoedkeuring
  AICopilotPanel.tsx          ← Sidebar chat via WebSocket
  AICopilotPanel.stories.tsx
  focus-builder/AICopilot.tsx ← In-page flow generator
  MissionProposalModal.tsx    ← 3-staps HITL approval modal
  CopilotSidebar.tsx          ← Layout wrapper voor de sidebar

  hooks/
    useAICopilot.ts           ← SSE-gebaseerde chat (fetch + SSE stream)
    useCopilotWebSocket.ts    ← WebSocket-gebaseerde chat

  services/
    copilotService.ts         ← Intent parsing via Serena Agent (Tool Broker)

  stores/
    useCopilotStore.ts        ← Zustand store: berichten, open/closed state

  types/
    copilot.ts                ← TypeScript types: MissionPlan, MissionStep, etc.

BACKEND
  src/core/api/
    copilot_endpoints.py      ← POST /api/v1/intents/parse (NLU, regex-based)
    copilot_websocket_endpoints.py ← WS /ws/copilot/chat + /ws/copilot/stats
    v1/ai_copilot/router.py   ← POST /api/v1/ai-copilot/suggest-tools (SSE)

  src/core/orchestrator/
    copilot_orchestrator.py   ← Multi-agent taakcoordinatie (golf-gebaseerde parallelisatie)

  tests/
    unit/test_copilot_endpoints.py
    unit/test_copilot_ws_import.py
    integration/test_api/test_ai_copilot.py
    integration/test_copilot_websocket.py
    integration/api/test_websocket_copilot.py
```

### Dataflow (huidige implementatie)

```
Gebruiker typt vraag
        |
        v
[CommandPalette / AICopilotPanel]
        |
        |-- (SSE path) POST /api/v1/ai-copilot/suggest-tools
        |       |-- LLMProviderFactory.get_llm_provider()
        |       |-- stream_response(prompt) --> SSE chunks
        |
        |-- (WS path) WS /ws/copilot/chat
        |       |-- websocket_auth (optioneel)
        |       |-- LLMProviderFactory.get_llm_provider()
        |       |-- stream_response(conversation_history) --> JSON chunks
        |
        |-- (NLU path) POST /api/v1/intents/parse
                |-- IntentParserService.parse() (regex, lokaal)
                |-- Geeft ParsedIntent terug (agent type, confidence, scopes)

[MissionProposalModal]
        |-- parseIntentAndGetProposal() -- MOMENTEEL MOCK API
        |-- Toont 3-staps approval flow
        |-- Stuurt CreateMissionPayload -- MOMENTEEL MOCK API CALL
```

---

## 3. Bestandsbeschrijvingen en huidige implementatiestaat

### 3.1 Backend

#### `src/core/api/copilot_endpoints.py`
- **Route:** `POST /api/v1/intents/parse`
- **Auth:** `get_current_user` (vereist)
- **Functie:** Regex-gebaseerde NLU: matcht query op patronen voor WORKFLOW / MEMORY / GOVERNANCE / SPECIALIST agent types
- **Input:** `IntentRequest { query: str (5-500 chars), context: dict | None }`
- **Output:** `IntentParseResponse { success, intent: ParsedIntent, execution_time_ms }`
- **Opmerking:** De `db: AsyncSession` dependency wordt geïnjecteerd maar nooit gebruikt (wasteful)
- **Opmerking:** Logging mist `tenant_id`

#### `src/core/api/copilot_websocket_endpoints.py`
- **Routes:** 
  - `WS /ws/copilot/chat` — streaming chat
  - `WS /ws/copilot/stats` — live statistieken
- **Auth chat-endpoint:** OPTIONEEL — token query-param, maar verbinding wordt ook geaccepteerd zonder token (anoniem)
- **Auth stats-endpoint:** `websocket_auth.authenticate_connected_user()` (vereist)
- **Functie:** Real-time streaming AI-chat met conversatiegeschiedenis, LLM-provider via factory
- **Protocol:**
  - Client → Server: `{ type: "message", content: string, model: string }`
  - Server → Client: `{ type: "chunk", content: string }` (streaming)
  - Server → Client: `{ type: "done", full_response: string }`
  - Server → Client: `{ type: "error", message: string }`
  - Client → Server: `{ type: "clear" }` / `{ type: "ping" }`
- **Conversatiegeheugen:** In-memory per WS-sessie, ONBEGRENSD
- **LLM:** DeepSeek via `get_llm_provider()`, ondersteunt ook fallback

#### `src/core/api/v1/ai_copilot/router.py`
- **Route:** `POST /api/v1/ai-copilot/suggest-tools`
- **Auth:** `get_current_user` (vereist)
- **Functie:** SSE streaming — LLM response + tool suggestions
- **Output:** SSE events: `reasoning`, `text`, `data` (tools), `finish`, `error`
- **Tool suggesties:** Momenteel hardcoded mock (KnowledgeBase, WorkflowEngine)
- **Opmerking:** Geen tenant_id logging, `current_user: Any` type

#### `src/core/orchestrator/copilot_orchestrator.py`
- **Klasse:** `CopilotOrchestrator`
- **Functie:** Wave-gebaseerde parallelle taakuitvoering via subagents
- **Dependency-resolutie:** Topologisch sorteren + golf-executie
- **Subagent executor:** Vereist dependency injection (werkt NIET standalone)
- **Gebruikt door:** Bedoeld voor gebruik vanuit de hoofd-chat-agent, niet via HTTP

### 3.2 Frontend

#### `frontend/src/hooks/useAICopilot.ts`
- Stuurt `POST /api/v1/ai-copilot/suggest-tools` via fetch
- Leest access token via `TokenStorage.getAccessToken()` — **verouderd patroon** (zie §5)
- SSE-parsing in handgeschreven loop
- Geen `useCallback` cleanup op unmount

#### `frontend/src/hooks/useCopilotWebSocket.ts`
- WebSocket-gebaseerde chat
- Delegeert naar `useWebSocket` hook (met `autoReconnect: true`)
- **Geen `mountedRef` guard** — kan reconnect-loop veroorzaken na unmount
- `message: any` type, `sendMessage({...} as any)` cast

#### `frontend/src/services/copilotService.ts`
- `parseIntent()` → delegeert naar `SerenaService.executeTool('serena__chat', ...)`
- `chat()` → idem
- Context-object bevat optioneel `tenant_id` veld — **dit mag nooit van de client komen**
- Type `ParsedIntent` heeft veld `suggested_actions` dat backend niet levert

#### `frontend/src/lib/stores/useCopilotStore.ts`
- Zustand store
- `sendMessage()` → `CopilotService.chat()` → Serena Agent
- Berichten groeien onbegrensd in de array
- Geen maximum conversatielengte

#### `frontend/src/components/copilot/CommandPalette.tsx`
- `Cmd+K` shortcut geregistreerd
- `MAX_QUERY_LENGTH = 500`
- Recente queries opgeslagen in `localStorage` (sleutel: `copilot_recent_queries`)
- `apiEndpoint` prop default: `/api/copilot/parse-intent` — **verkeerd pad** (zou `/api/v1/intents/parse` moeten zijn)
- Maakt mock `MissionPlan` lokaal aan na NLU response
- Heeft geen auth-header op de fetch call

#### `frontend/src/components/copilot/MissionProposalModal.tsx`
- Goed getypeerd, Radix UI Dialog
- `parseIntentAndGetProposal()` is een **volledige mock** (setTimeout + hardcoded data)
- Mission submit is ook een **mock** (setTimeout, geen echte API-call)
- `tenantId` prop accepteert van parent — in productie moet dit uit JWT komen
- Compliance checks zijn statische mockdata

#### `frontend/src/components/focus-builder/AICopilot.tsx`
- Simpele textarea + generate button
- `onGenerate: (graph: any) => void` — `any` type
- Inline styles (`style={{ padding: '10px' }}`) — schending Tailwind-only regel
- `alert()` op fout — moet vervangen worden door een Toast/notification
- Geen validatie op prompt-lengte

---

## 4. Beveiligingsaudit — Bevindingen

### KRITIEK

#### K-1: Unauthenticated WebSocket toegang tot LLM
**Bestand:** `copilot_websocket_endpoints.py:51-92`  
**Probleem:** De `token` query-parameter is optioneel. Als er geen token is, wordt de WS-verbinding toch geaccepteerd en kan de LLM onbeperkt worden aangeroepen als anonieme gebruiker. Dit betekent: gratis LLM-credits voor iedereen zonder account.

```python
# HUIDIG (fout)
async def copilot_chat_websocket(websocket: WebSocket, token: str | None = None):
    await get_ws_manager().connect(websocket)
    if token:
        current_user = await get_current_user_ws(websocket)
    # Geen token = connectie toch geaccepteerd als anonymous
```

**Fix:**
```python
async def copilot_chat_websocket(websocket: WebSocket, token: str | None = None):
    await get_ws_manager().connect(websocket)
    try:
        current_user = await get_current_user_ws(websocket)
        set_tenant_id(current_user.tenant_id)
    except Exception:
        get_ws_manager().disconnect(websocket)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
```

---

### HOOG

#### H-1: Frontend stuurt `tenant_id` in request body
**Bestand:** `copilotService.ts:13`  
**Probleem:** `context?: { tenant_id?: string }` is een client-controlled veld. De backend mag dit NOOIT vertrouwen als authoritatieve bron van tenant-identificatie (CLAUDE.md regel 6, ADR-003).  
**Fix:** Verwijder `tenant_id` uit het `IntentRequest.context` type en schema. Backend leest tenant_id altijd uit JWT via `require_tenant_id()`.

#### H-2: Interne fouten lekken naar WebSocket clients
**Bestand:** `copilot_websocket_endpoints.py:158, 229`  
**Probleem:** Provider-fouten en streaming-fouten worden letterlijk doorgestuurd naar de client.
```python
"message": f"Provider initialization failed: {str(e)}"  # Lekt intern pad/SDK info
"message": f"Streaming failed: {str(e)}"
```
**Fix:** Generieke berichten. Interne details alleen naar server-side log.
```python
logger.error("Provider init failed: %s", e, exc_info=True)
await websocket.send_json({"type": "error", "message": "AI service unavailable"})
```

#### H-3: Geen rate limiting op WebSocket
**Bestand:** `copilot_websocket_endpoints.py`  
**Probleem:** Een ingelogde gebruiker kan de LLM in een loop aanroepen zonder enige beperking. Geen per-user, per-tenant of per-connectie throttle.  
**Fix:** Voeg een token-bucket-gebaseerde rate limiter toe per `user_id` en `tenant_id`. Of begrens het aantal berichten per WS-sessie.

#### H-4: Geen `mountedRef` guard in WebSocket hook
**Bestand:** `useCopilotWebSocket.ts`  
**Probleem:** CLAUDE.md regel 14 (WebSocket hooks) vereist een `mountedRef` guard. Zonder guard triggert `autoReconnect` na unmount een reconnect-loop.  
**Fix:**
```typescript
const mountedRef = useRef(false);
useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
}, []);
// In onclose handler: if (!mountedRef.current) return;
```

#### H-5: Geen bericht-groottelimiet op WebSocket
**Bestand:** `copilot_websocket_endpoints.py:125`  
**Probleem:** `user_message = message_data.get("content", "").strip()` — geen max-lengte. De HTTP intent-endpoint heeft wel 500 char limiet, maar WS accepteert berichten van onbeperkte grootte.  
**Fix:**
```python
MAX_MESSAGE_LENGTH = 2000
user_message = message_data.get("content", "").strip()[:MAX_MESSAGE_LENGTH]
```

#### H-6: CommandPalette heeft geen auth-header
**Bestand:** `CommandPalette.tsx:141-145`  
**Probleem:** De `fetch(apiEndpoint, ...)` call stuurt geen `Authorization` header. Werkt alleen als backend cookie-auth accepteert, maar is fragiel.  
**Fix:** Voeg Authorization header toe (of verifieer dat cookie-flow dit afdekt).

---

### MIDDEL

#### M-1: Conversatiegeschiedenis onbegrensd in memory
**Bestand:** `copilot_websocket_endpoints.py:102`  
**Probleem:** `conversation_history: list[LLMMessage] = [...]` groeit per WS-sessie oneindig. Lange sessies → hoge LLM token-kosten + mogelijke OOM.  
**Fix:** Begrens op bijv. 20 berichten (sliding window):
```python
MAX_HISTORY = 20
conversation_history.append(LLMMessage(role="user", content=user_message))
if len(conversation_history) > MAX_HISTORY + 1:  # +1 voor system prompt
    conversation_history = [conversation_history[0]] + conversation_history[-(MAX_HISTORY):]
```

#### M-2: `any` types op meerdere plekken (schending CLAUDE.md)

| Bestand | Probleem | Fix |
|---------|---------|-----|
| `useAICopilot.ts:121` | `catch (err: any)` | `catch (err: unknown)` |
| `useCopilotWebSocket.ts:32` | `(message: any)` | definieer `CopilotWSMessage` type |
| `useCopilotWebSocket.ts:101` | `sendMessage({...} as any)` | verwijder cast |
| `AICopilot.tsx:8` | `onGenerate: (graph: any)` | definieer `FlowGraph` type |
| `v1/ai_copilot/router.py:110` | `current_user: Any` | gebruik `UserResponse` |

#### M-3: `db` dependency geïnjecteerd maar nooit gebruikt
**Bestand:** `copilot_endpoints.py:311`  
**Probleem:** `db: AsyncSession = Depends(get_db)` opent een database-connectie die ongebruikt blijft.  
**Fix:** Verwijder de dependency volledig.

#### M-4: F-string logging
**Bestand:** `copilot_endpoints.py:211, 394`  
**Fix:** Vervang f-strings door `%s` formatting voor structured logging.

#### M-5: Debug-prefix logs in productiecode
**Bestand:** `copilot_websocket_endpoints.py:56, 273`  
`"COPILOT_DEBUG: Chat WS Request..."` → verwijderen of naar `logger.debug()`.

#### M-6: Tenant_id ontbreekt in audit logs
**Bestand:** `copilot_endpoints.py:378`  
**Fix:** Voeg `tenant_id=current_user.tenant_id` toe aan alle `logger.info/error` calls in copilot-endpoints.

#### M-7: Berichten in Zustand store onbegrensd
**Bestand:** `useCopilotStore.ts:41`  
**Fix:**
```typescript
messages: [...state.messages, message].slice(-100)
```

#### M-8: CommandPalette slaat recente queries op in localStorage
**Bestand:** `CommandPalette.tsx:54, 199`  
**Probleem:** `localStorage` is niet veilig voor gevoelige AI-queries. Overweeg server-side opslag (per user) of in-memory only.

#### M-9: `CommandPalette` default `apiEndpoint` is verkeerd
**Bestand:** `CommandPalette.tsx:61`  
```typescript
apiEndpoint = '/api/copilot/parse-intent'  // bestaat niet
// moet zijn:
apiEndpoint = '/api/v1/intents/parse'
```

---

### LAAG

#### L-1: Gefragmenteerde router-architectuur
Er zijn drie overlappende copilot HTTP-endpoints zonder duidelijk eigendom:
- `POST /api/v1/intents/parse` — regex-NLU
- `POST /api/v1/ai-copilot/suggest-tools` — SSE streaming
- `WS /ws/copilot/chat` — WebSocket streaming

De twee HTTP-endpoints doen deels hetzelfde (NLU + LLM-response). Overweeg consolidatie naar één coherente Copilot API.

#### L-2: `AICopilot.tsx` (focus-builder) gebruikt inline styles en `alert()`
```tsx
style={{ padding: '10px', background: '#f0f8ff' }}  // schending Tailwind-only
alert("AI Generation request sent...")              // vervang door Toast
```

#### L-3: `useAICopilot.ts` leest token via `TokenStorage` (verouderd)
Per CLAUDE.md §13.1 (Phase 5) mogen access tokens niet meer uit localStorage komen — de httpOnly cookie-flow handelt dit automatisch af. De SSE-hook stuurt nog een expliciete `Authorization: Bearer` header.

#### L-4: `copilot_orchestrator.py` heeft verkeerde docstring
De docstring zegt "GitHub Copilot Orchestrator" — dit is SanskritiSetu's eigen orchestrator.

#### L-5: `MissionProposalModal` accepteert `tenantId` als prop
In productie moet `tenantId` uit de JWT komen, niet als React-prop van de parent.

---

## 5. Wat er NOG NIET gebouwd is (Productiegaten)

### 5.1 Mock → Echte implementatie

| Component | Huidig | Moet worden |
|-----------|--------|------------|
| `MissionProposalModal.parseIntentAndGetProposal()` | Mock met `setTimeout` + hardcoded stappen | Echte `POST /api/v1/intents/parse` call |
| `MissionProposalModal.handleSubmit()` | Mock met `setTimeout` | Echte `POST /api/v1/missions` call |
| `v1/ai_copilot/router.py` tool suggestions | Hardcoded `[KnowledgeBase, WorkflowEngine]` | Dynamisch vanuit Tool Broker / AgentRouter |
| `CommandPalette.tsx` apiEndpoint | Verkeerd pad, geen auth | Correct pad + auth header |

### 5.2 Ontbrekende features voor productiekwaliteit

1. **Rate limiting op WebSocket** — ontbreekt volledig
2. **Conversatievenster begrenzing** — ontbreekt (onbegrensd geheugen)
3. **WebSocket authenticatie** — optioneel i.p.v. verplicht
4. **Tenant-scoped conversatiehistorie** — conversatiegeschiedenis leeft alleen in WS-sessie, geen persistentie
5. **Serena Agent integratie** — `copilotService.ts` delegeert naar SerenaService, maar de WS-endpoint gebruikt directe LLM-provider. Twee parallelle implementaties zonder synchronisatie
6. **Mission execution** — het goedkeuren van een missie in de modal doet nog niets (mock)
7. **Tool Broker integratie** — Copilot gebruikt geen ToolBroker (ADR-015: allowlist + HITL gate)
8. **AgentRouter integratie** — Copilot kiest geen agent via de `AgentRouterAgent` (ADR-023)
9. **Audit trail** — copilot-gesprekken worden niet in de AuditLog opgeslagen
10. **Gebruikersgeschiedenis** — recente queries staan in localStorage, niet server-side
11. **Scope-validatie** — NLU geeft `required_scopes` terug, maar de frontend controleert deze niet voordat het verzoek wordt ingediend (alleen in `MissionProposalModal.Step3_Confirmation`)

### 5.3 Architecturele schuld

- **Twee streaming-implementaties:** `useAICopilot.ts` (SSE) en `useCopilotWebSocket.ts` (WebSocket) zijn beide beschikbaar maar doen hetzelfde. `AICopilotPanel.tsx` gebruikt de WS-versie; de SSE-versie lijkt de oudere implementatie te zijn.
- **Twee NLU-implementaties:** `copilotService.ts` → Serena Agent vs. `copilot_endpoints.py` → lokale regex. Het is onduidelijk welke leidend is.
- **`CopilotOrchestrator` niet geïntegreerd:** Het orchestrator-bestand bestaat maar wordt nergens aangeroepen vanuit de HTTP/WS endpoints. Het is een standalone module.

---

## 6. De Gewenste Doelarchitectuur

Op basis van het originele voorstel (`downloads/voorstel copilot.txt`) en de ADR-architectuur:

### 6.1 Copilot als Platform Guardian

De Copilot moet worden een **tenant-agnostische Platform Guardian Copilot** met:

- **Persona:** Proactieve assistent, denkt als senior solution architect
- **Taaldetectie:** Antwoordt altijd in de taal van de gebruiker
- **Page-aware:** Past suggesties aan op de huidige route (`/workflows`, `/agents`, etc.)
- **Tool-first:** Gebruik altijd tools boven gokken voor tenant-data
- **JSON-only output contract:**
  ```json
  {
    "message": "<uitleg in gebruikerstaal>",
    "action": "<tool-naam of null>",
    "action_params": { "tenant_id": "...", ... },
    "confidence": 0.85
  }
  ```

### 6.2 Master System Prompt Structuur

De system prompt moet parametriseerbaar zijn:

```python
MASTER_PROMPT_TEMPLATE = """
You are the Platform Guardian Copilot for {platform_name}.

Platform context: {tenant_domain}, tenant_id: {tenant_id}
Tech stack: FastAPI, Next.js, Docker + Traefik
Current user language: {user_language}
Current route: {current_route}
Page context: {page_context}
Time: {current_time_iso}

Available tools:
{tools_description_block}

Response contract: always valid JSON with keys: message, action, action_params, confidence.
Multi-tenant safety: every tool call MUST include tenant_id.
"""
```

### 6.3 Tools / Skills die de Copilot moet kunnen aanroepen

| Tool | Beschrijving | Vereist |
|------|-------------|---------|
| `search_knowledge_base` | Hybride zoek in tenant-kennisbank | Nee (post-MVP) |
| `send_notification` | In-app notificatie sturen | Nee (post-MVP) |
| `create_workflow` | Nieuwe workflow aanmaken | Nee (post-MVP) |
| `navigate_to` | Navigeer gebruiker naar een route | Ja (MVP) |
| `get_system_status` | Gezondheid agents/workflows opvragen | Ja (MVP) |
| `search_workflows` | Bestaande workflows zoeken | Ja (MVP) |
| `parse_intent` | NLU via backend | Ja (MVP — al gebouwd) |
| `propose_mission` | Missieplan genereren | Ja (MVP) |
| `approve_mission` | Missie goedkeuren + starten | Ja (MVP) |

### 6.4 Correcte dataflow (doelarchitectuur)

```
Gebruiker → CommandPalette / AICopilotPanel
              |
              v
    POST /api/v1/copilot/chat  (enkelvoudig geconsolideerd endpoint)
         |-- Auth: JWT verplicht (cookie-flow)
         |-- Rate limit: per user_id + tenant_id
         |-- tenant_id: altijd uit JWT, nooit uit request body
              |
              v
    UltimateCVAAgent (of CopilotService)
         |-- get_system_prompt(tenant_context, route_context, tools)
         |-- LLM call via provider factory (DeepSeek primair)
         |-- Tool calls via ToolBroker (ADR-015 allowlist)
         |-- Agent routing via AgentRouterAgent (ADR-023)
              |
              v
    JSON response: { message, action, action_params, confidence }
         |
         v
    Frontend: action uitvoeren (navigate, propose_mission, etc.)
    HITL: missions vereisen gebruikersgoedkeuring voor uitvoering
```

---

## 7. Perfectie Roadmap — Geprioriteerde Taken

### Fase 0 — Bugfixes (KRITIEK, doen voor elke push naar main)

| # | Taak | Bestand | Geschat |
|---|------|---------|---------|
| 0.1 | Maak WS-auth verplicht, weiger verbinding zonder geldig JWT | `copilot_websocket_endpoints.py` | 30 min |
| 0.2 | Vervang interne foutberichten door generieke tekst | `copilot_websocket_endpoints.py` | 15 min |
| 0.3 | Verwijder `tenant_id` uit frontend context-object | `copilotService.ts` + `types/copilot.ts` | 15 min |
| 0.4 | Herstel `apiEndpoint` default in CommandPalette | `CommandPalette.tsx` | 5 min |
| 0.5 | Voeg auth-header toe aan CommandPalette fetch | `CommandPalette.tsx` | 15 min |

### Fase 1 — Hardening (HOOG, sprint 1)

| # | Taak | Bestand | Geschat |
|---|------|---------|---------|
| 1.1 | Voeg rate limiting toe op WS-endpoint (per user + tenant) | `copilot_websocket_endpoints.py` | 2u |
| 1.2 | Begrens conversatiegeschiedenis (max 20 berichten, sliding window) | `copilot_websocket_endpoints.py` | 30 min |
| 1.3 | Voeg max-berichtlengte toe op WS-input (2000 chars) | `copilot_websocket_endpoints.py` | 15 min |
| 1.4 | Implementeer `mountedRef` guard in `useCopilotWebSocket` | `useCopilotWebSocket.ts` | 30 min |
| 1.5 | Verwijder alle `any` types (5 locaties) | Meerdere bestanden | 1u |
| 1.6 | Verwijder ongebruikte `db` dependency | `copilot_endpoints.py` | 5 min |
| 1.7 | Fix f-string logging → `%s` formatting + voeg `tenant_id` toe | `copilot_endpoints.py` | 15 min |
| 1.8 | Verwijder COPILOT_DEBUG log-regels | `copilot_websocket_endpoints.py` | 5 min |
| 1.9 | Begrens Zustand message array (max 100) | `useCopilotStore.ts` | 5 min |
| 1.10 | Fix inline styles + `alert()` in `AICopilot.tsx` | `focus-builder/AICopilot.tsx` | 30 min |

### Fase 2 — Consolidatie (MIDDEL, sprint 2)

| # | Taak | Beschrijving |
|---|------|-------------|
| 2.1 | Consolideer NLU naar één implementatie | Kies: Serena Agent OF regex-NLU, verwijder de andere |
| 2.2 | Consolideer streaming naar WebSocket | Depreceer SSE (`useAICopilot.ts`, `suggest-tools` endpoint) |
| 2.3 | Verbind `MissionProposalModal` met echte API | Vervang mocks door echte `POST /api/v1/intents/parse` + `POST /api/v1/missions` |
| 2.4 | Verplaats recente queries van localStorage naar server-side | `GET /api/v1/copilot/history` endpoint, tenant+user scope |
| 2.5 | Integreer Tool Broker (ADR-015) | Alle tool-calls via ToolBroker allowlist, niet direct |
| 2.6 | Integreer AgentRouter (ADR-023) | Copilot gebruikt `AgentRouterAgent` voor agent-selectie op basis van intent |

### Fase 3 — Uitbreiding (sprint 3+)

| # | Taak | Beschrijving |
|---|------|-------------|
| 3.1 | Master System Prompt implementeren | Tenant-agnostisch, parametriseerbaar, taaldetectie |
| 3.2 | `search_knowledge_base` tool | Hybride zoek via bestaande vector store |
| 3.3 | `send_notification` tool | Via bestaande `notification_service` |
| 3.4 | Mission execution koppeling | Goedgekeurde missies starten echte agentworkflows |
| 3.5 | Audit trail voor copilot-gesprekken | AuditLog entries per bericht (via `best_effort`) |
| 3.6 | Scope-validatie in frontend | Blokkeer submission als gebruiker niet de vereiste scopes heeft |
| 3.7 | Copilot persistentie | Conversatiegeschiedenis per user in database (tenant-isolated) |

---

## 8. Testdekking — Huidige staat en hiaten

### Bestaande tests

| Bestand | Type | Dekt |
|---------|------|------|
| `tests/unit/test_copilot_endpoints.py` | Unit | Intent parser endpoints |
| `tests/unit/test_copilot_ws_import.py` | Unit | WS module-import smoke test |
| `tests/integration/test_api/test_ai_copilot.py` | Integratie | SSE endpoint |
| `tests/integration/test_copilot_websocket.py` | Integratie | WS chat |
| `tests/integration/api/test_websocket_copilot.py` | Integratie | WS protocol |
| `frontend/src/components/copilot/CommandPalette.test.tsx` | Frontend unit | CommandPalette |
| `frontend/src/components/copilot/__tests__/CommandPalette.test.tsx` | Frontend unit | Duplicaat? |
| `frontend/src/components/focus-builder/__tests__/AICopilot.test.tsx` | Frontend unit | AICopilot widget |
| `frontend/src/hooks/__tests__/useUserAICopilot.test.ts` | Frontend unit | Hook tests |
| `frontend/src/lib/stores/__tests__/useCopilotStore.test.ts` | Frontend unit | Store tests |
| `frontend/tests/integration/copilot-mission.integration.test.tsx` | Frontend integratie | Mission flow |

### Ontbrekende tests (moet worden toegevoegd)

1. **Security test: WS zonder token wordt geweigerd** (na fix van K-1)
2. **Security test: `tenant_id` in body wordt genegeerd** (na fix van H-1)
3. **Rate limit test: meer dan N berichten per minuut geeft 429 of WS-fout**
4. **Conversatievenster test: history blijft begrensd na 25+ berichten**
5. **Frontend test: `mountedRef` voorkomt reconnect na unmount**
6. **Tenant-isolatie test: user van tenant A ziet geen conversatie van tenant B**
7. **Integratie test: `CommandPalette` → `POST /api/v1/intents/parse` → response** (geen mock)
8. **Behavioral test: "Gebruiker typt query, ziet NLU-respons met correct agent-type"**

---

## 9. Projectregels die altijd van toepassing zijn

De volgende regels uit `CLAUDE.md` zijn bindend voor alle aanpassingen aan de Copilot:

1. **tenant_id altijd uit JWT**, nooit uit request body of query-param
2. **Geen hardcoded URLs of secrets** — altijd `os.getenv()`
3. **`datetime.now(timezone.utc)`** — nooit `datetime.now()` of `datetime.utcnow()`
4. **`best_effort`** voor alle AuditLog-writes
5. **`select()` + `await db.execute()`** voor alle DB-queries
6. **Geen `any` types** in TypeScript — gebruik `unknown` + type guard
7. **`useEffect` cleanup** voor timers, intervals, WS-listeners
8. **`mountedRef` guard** voor WebSocket hooks
9. **Logging:** altijd `tenant_id` + `user_id` + `exc_info=True` bij fouten
10. **Paginering** op alle list-endpoints (limit/offset)
11. **Geen `DEBUG`** — gebruik `APP_DEBUG`
12. **Migraties:** altijd in actieve Alembic-keten, werkende `downgrade()`
13. **Pytest:** altijd `--stepwise` bij volledige runs
14. **Message broker:** Dramatiq + Redis (geen RabbitMQ)
15. **Edge gateway:** Traefik (geen Nginx)
16. **Tenant identity:** JWT claim via ContextVar (geen X-Tenant-ID header)

---

## 10. Sleutelbestanden Samenvatting

| Bestand | Rol | Prioriteit aanpassen |
|---------|-----|---------------------|
| `src/core/api/copilot_websocket_endpoints.py` | WS chat + stats | KRITIEK (auth, rate limit, error handling) |
| `src/core/api/copilot_endpoints.py` | NLU parse endpoint | MIDDEL (logging, db cleanup) |
| `src/core/api/v1/ai_copilot/router.py` | SSE streaming (verouderd?) | LAAG (consolideer of depreceer) |
| `src/core/orchestrator/copilot_orchestrator.py` | Taakcoordinatie | LAAG (integreer of documenteer) |
| `frontend/src/hooks/useCopilotWebSocket.ts` | WS hook | HOOG (mountedRef, types) |
| `frontend/src/hooks/useAICopilot.ts` | SSE hook (verouderd?) | LAAG (consolideer of depreceer) |
| `frontend/src/services/copilotService.ts` | Intent + chat service | KRITIEK (verwijder tenant_id) |
| `frontend/src/lib/stores/useCopilotStore.ts` | Zustand state | MIDDEL (begrens messages) |
| `frontend/src/components/copilot/CommandPalette.tsx` | Cmd+K UI | HOOG (auth, apiEndpoint) |
| `frontend/src/components/copilot/MissionProposalModal.tsx` | 3-staps HITL modal | MIDDEL (replace mocks) |
| `frontend/src/components/focus-builder/AICopilot.tsx` | In-page widget | LAAG (inline styles, alert) |
| `frontend/src/types/copilot.ts` | TypeScript types | MIDDEL (verwijder tenant_id) |

---

*Document gegenereerd op basis van codebase-audit 2026-05-22. Alle bestandspaden zijn relatief aan de repo-root `SanskritiSetu.org/`.*
