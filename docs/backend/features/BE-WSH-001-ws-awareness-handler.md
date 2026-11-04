# Backend Feature Specification

## Metadata

- Feature ID: BE-WSH-001
- Feature naam: WebSocket Awareness Handler
- Status: Draft
- Auteur: AI Agent
- Reviewer: TBD
- Datum: 2026-05-29
- Gerelateerde user story / ticket: SP-E02 Dag 2
- Gerelateerde router / module: src/core/api/v1/sync/ws_handler.py
- Gerelateerde frontend endpoints: ws://host/api/v1/sync/ws/awareness/{workflow_id}
- Gerelateerde database tabellen: Geen (Redis hash)
- Versie: 1.0

---

## Doel en scope

### Doel

Biedt een real-time WebSocket endpoint voor collaboratieve awareness updates in workflow editing. Clients pushen cursor positie, selectie en presence status naar de server; de server schrijft deze naar Redis waar andere clients ze ophalen via het bestaande HTTP GET awareness endpoint.

### In scope

- WebSocket endpoint `/api/v1/sync/ws/awareness/{workflow_id}`
- JWT auth via WebSocketAuthenticator (cookie / query param / subprotocol)
- Subprotocol negotiation (`json`)
- Message validation (cursor, selection, presence)
- Redis HSET + EXPIRE pipeline (30s TTL)
- HDEL cleanup on disconnect
- Graceful error handling (error messages naar client)

### Out of scope

- Broadcasting awareness updates naar andere WS clients (pull model via HTTP)
- Per-field TTL in Redis (Redis hashes ondersteunen dit niet)
- Rate limiting op WS niveau (HTTP endpoints hebben rate limiting)
- Presence heartbeat mechanism (client-side verantwoordelijkheid)

---

## Build summary

- Nieuw gebouwd:
  - `src/core/api/v1/sync/ws_handler.py` — awareness_websocket handler
  - `tests/unit/sync/test_ws_awareness.py` — 19 unit tests
  - `tests/integration/sync/test_ws_awareness_integration.py` — 3 integratietests
- Gewijzigd:
  - `src/core/api/router_registry.py` — sync_ws_router registratie
- Verwijderd: —
- Beinvloede bestaande flows:
  - `GET /api/v1/sync/awareness/{workflow_id}` leest nu entries geschreven door WS

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-WSH-001 | WebSocket Awareness Handler | WS endpoint | src/core/api/v1/sync/ws_handler.py | Nieuw | Real-time collaboration |
| BE-WSH-002 | _AwarenessMessageValidator | Validator class | src/core/api/v1/sync/ws_handler.py | Nieuw | Message type/payload validatie |

---

## API-flows

### Flow ID: BE-FLW-004 — Awareness update via WebSocket

- Trigger: Client opent WS naar `/api/v1/sync/ws/awareness/{workflow_id}`
- Voorwaarden: Geldige JWT (via cookie, query param, of subprotocol)
- Request-pad:
  1. `WebSocketAuthenticator.authenticate()` — JWT verificatie
  2. `workflow_id` regex validatie (`^[\w\-]+$")
  3. `receive_json()` — client stuurt awareness update
  4. `_AwarenessMessageValidator.validate()` — type + payload controle
- Service-stappen:
  1. Bouw awareness entry JSON: `{user_id, type, payload, updated_at}`
  2. Redis pipeline: `HSET awareness:{tenant_id}:{workflow_id} {user_id} {json}` + `EXPIRE key 30`
  3. `await pipe.execute()`
  4. Stuur ack naar client: `{"type": "ack", "ts": <epoch_ms>}`
- DB-operaties: Geen (Redis only)
- Successtatus + response: WS ack message
- Foutpaden:
  - 4001: Geen auth token
  - 4002: Ongeldige / verlopen token
  - 4003: Ongeldig workflow_id formaat
  - WS error: Ongeldig message type of payload

### Flow ID: BE-FLW-005 — WebSocket disconnect cleanup

- Trigger: Client sluit WS verbinding
- Service-stappen:
  1. `WebSocketDisconnect` exception in while loop
  2. `finally` block: `HDEL awareness:{tenant_id}:{workflow_id} {user_id}`
  3. `_auth.disconnect(user_id)` — verwijder uit connection tracker
- Successtatus: Stille cleanup, geen response naar client

---

## Detaildocumentatie per artefact

---

## [BE-WSH-001] WebSocket Awareness Handler

### 1. Type

WebSocket endpoint (FastAPI `@router.websocket`)

### 2. Locatie

- Bestandspad: src/core/api/v1/sync/ws_handler.py
- Router: APIRouter(prefix="/sync", tags=["sync"])
- Functie: awareness_websocket

### 3. Gerelateerde flow

BE-FLW-004, BE-FLW-005

### 4. Doel

Real-time awareness updates ontvangen van clients en persisteren in Redis voor ophalen door andere clients.

### 5. Functionele beschrijving

De handler accepteert WebSocket verbindingen, authenticeert via JWT, en verwerkt inkomende awareness updates. Elke update wordt geschreven naar een Redis hash met 30 seconden TTL. Bij disconnect wordt de user's entry opgeruimd.

### 6. Technische beschrijving

```python
@router.websocket("/ws/awareness/{workflow_id}")
async def awareness_websocket(websocket: WebSocket, workflow_id: str) -> None:
    # Auth + subprotocol negotiation
    user = await _auth.authenticate(websocket)
    # workflow_id regex validation
    # Redis HSET + EXPIRE pipeline per message
    # HDEL cleanup in finally block
```

**Message format (client → server):**
```json
{"type": "cursor", "payload": {"x": 100, "y": 200, "color": "#ff0000"}}
{"type": "selection", "payload": {"node_ids": ["a", "b"]}}
{"type": "presence", "payload": {"status": "active"}}
```

**Response format (server → client):**
```json
{"type": "ack", "ts": 1780012947105}
{"type": "error", "message": "Invalid type 'hacked'. Allowed: cursor, presence, selection"}
```

**Redis data structuur:**
- Key: `awareness:{tenant_id}:{workflow_id}`
- Field: `{user_id}`
- Value: JSON string `{"user_id": "...", "type": "...", "payload": {...}, "updated_at": <epoch_ms>}`
- TTL: 30 seconden (op de hele hash key)

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Ja (JWT via cookie, query param, of Sec-WebSocket-Protocol)
- Vereiste rol / scope: Standaard gebruiker
- Tenant-isolatie: `tenant_id` uit JWT claim, Redis key scoped per tenant
- Feature flag: Nee

### 8. Request-specificatie

**WebSocket handshake:**
- URL: `ws://host/api/v1/sync/ws/awareness/{workflow_id}`
- Subprotocols: `json` (preferred)
- Auth methods (in priority order):
  1. Cookie: `access_token=<jwt>`
  2. Query param: `?token=<jwt>`
  3. Sec-WebSocket-Protocol: `access_token, <jwt>`
  4. Header: `Authorization: Bearer <jwt>`

**Message schema:**
- `type`: enum("cursor", "selection", "presence")
- `payload`: object (dict), max 64KB serialized

### 9. Response-specificatie

**Ack (succes):**
```json
{"type": "ack", "ts": 1780012947105}
```

**Error (validatie fout):**
```json
{"type": "error", "message": "Invalid type 'evil'. Allowed: cursor, presence, selection"}
```

### 10. Validaties en constraints

- `workflow_id`: `^[\w\-]+$`
- `type`: alleen `cursor`, `selection`, `presence`
- `payload`: dict, max 64KB, max 2 niveaus nesting
- Redis entry JSON: max 64KB

### 11. Business rules

- TTL 30s verlengd bij elke update (EXPIRE op hele hash key)
- Inactieve users verdwijnen automatisch na 30s (Redis TTL) of direct bij disconnect (HDEL)
- Multi-user: meerdere users in zelfde hash, verschillende velden

### 12. Afhankelijkheden

- Redis (awareness state)
- JWT auth (WebSocketAuthenticator)
- FastAPI WebSocket support

### 13. Foutafhandeling

- **4001**: Geen auth token → WS close
- **4002**: Ongeldige token → WS close
- **4003**: Ongeldig workflow_id → WS close met reason
- **WS error**: Ongeldig message → error JSON naar client, verbinding blijft open
- **Redis fout**: Ongemerkt (geen error naar client), logging op WARNING niveau

### 14. Transacties en data-integriteit

- Redis pipeline: HSET + EXPIRE atomic
- Geen transacties (Redis is eventueel consistent)

### 15. Telemetry / logging / tracing

- INFO: `awareness_ws_connected`, `awareness_ws_disconnect`, `awareness_ws_cleanup`
- WARNING: `awareness_ws_error`, `awareness_ws_cleanup_failed`
- OpenTelemetry spans via FastAPI middleware

### 16. Caching

- Gecached: Nee (real-time data)

### 17. Acceptatiecriteria

- [x] WS endpoint accepteert cursor updates
- [x] WS endpoint accepteert selection updates
- [x] WS endpoint accepteert presence updates
- [x] Redis HSET + EXPIRE pipeline werkt
- [x] TTL is 30 seconden
- [x] HDEL cleanup bij disconnect
- [x] Ongeldig message type retourneert error JSON
- [x] Ongeldig workflow_id sluit WS met 4003
- [x] Auth failure sluit WS zonder accept
- [x] Subprotocol `json` wordt geselecteerd indien aangeboden

### 18. Integratoruitleg

- Open een WebSocket naar `/api/v1/sync/ws/awareness/{workflow_id}`
- Authenticatie via JWT cookie (canonical) of query param
- Stuur JSON messages: `{"type": "cursor", "payload": {"x": 100, "y": 200}}`
- Ontvang ack: `{"type": "ack", "ts": ...}`
- Bij fouten ontvang je error JSON; verbinding blijft open
- Disconnect verdwijderd je presence automatisch
- Andere clients lezen awareness via `GET /api/v1/sync/awareness/{workflow_id}`

### 19. Trainingssamenvatting

- Actor: Frontend applicatie / geauthenticeerde gebruiker
- Voorwaarde: Geldige JWT, open WebSocket verbinding
- Actie: Stuur awareness update JSON
- Systeemverwerking: Auth → Validatie → Redis HSET+EXPIRE → Ack
- Succesrespons: WS ack message
- Foutrespons: WS error message of close code 4001/4002/4003
- Uitzonderingen: Redis failure → geen error naar client (graceful degradation)

---

## [BE-WSH-002] _AwarenessMessageValidator

### 1. Type

Interne validator class (geen Pydantic)

### 2. Locatie

- Bestandspad: src/core/api/v1/sync/ws_handler.py

### 3. Gerelateerde flow

BE-FLW-004

### 4. Doel

Valideert inkomende WebSocket awareness messages zonder Pydantic overhead.

### 5. Functionele beschrijving

Controleert message type tegen allowlist en payload structuur. Flattened nested objects tot 2 niveaus. Reject oversized payloads.

### 6. Technische beschrijving

```python
class _AwarenessMessageValidator:
    ALLOWED_TYPES = {"cursor", "selection", "presence"}

    @classmethod
    def validate(cls, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        ...
```

### 7-16. Overige secties

Niet van toepassing (interne utility)

### 17. Acceptatiecriteria

- [x] Valideert dict input
- [x] Reject ongeldige types
- [x] Reject ontbrekende payload
- [x] Reject non-dict payload

---

## Integratorhandleiding

### Voor API-consumenten en koppelende teams

1. **Authenticatie**: JWT via cookie (`access_token`) of query param (`?token=xxx`).
2. **WebSocket URL**: `ws://host/api/v1/sync/ws/awareness/{workflow_id}`
3. **Subprotocol**: Bied `json` aan voor expliciete protocol selectie.
4. **Message types**: `cursor`, `selection`, `presence`
5. **Payload**: JSON object, max 64KB, max 2 niveaus nesting.
6. **Ack**: Server stuurt `{"type": "ack", "ts": ...}` na succesvolle verwerking.
7. **Errors**: Server stuurt `{"type": "error", "message": ...}` bij validatiefouten.
8. **Cleanup**: Disconnect verwijderd je entry automatisch uit Redis.
9. **Lezen**: Andere clients gebruiken `GET /api/v1/sync/awareness/{workflow_id}`.

---

## Open aannames

- Clients poll awareness via HTTP GET (geen WS broadcast)
- Redis is beschikbaar en bereikbaar
- Frontend hanteert eigen heartbeat om presence alive te houden
- Per-field TTL in Redis is niet beschikbaar; hele hash verdwijnt na 30s inactiviteit

## Open vragen

- Moet de server awareness updates broadcasten naar andere WS clients?
- Is een server-side heartbeat naar clients gewenst?

## Risico's

- Redis hash TTL verwijdert ALLE users als niemand 30s actief is (acceptabel voor MVP)
- Geen rate limiting op WS niveau (HTTP endpoints hebben dit wel)
- Grote aantal gelijktijdige WS verbindingen kan Redis belasten

---

## QA-checks

- [x] Endpoint functioneel getest (happy path) — 19 unit tests PASS
- [x] Alle foutstatus-codes getest — 4001, 4002, 4003, invalid type, invalid payload
- [x] Auth en permissies getest — mock auth met accept/close
- [x] Tenant-isolatie getest — Redis key scoped per tenant_id
- [x] Validaties getest — message type, payload, workflow_id
- [x] Edge cases getest — empty message, missing payload, non-dict input
- [x] Redis interactie getest — HSET, EXPIRE, HDEL, pipeline
- [ ] Performance / load getest — niet in scope
- [x] Logging en tracing gecontroleerd — INFO/WARNING logs aanwezig

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
- [ ] Review door reviewer-prompt: APPROVED of APPROVED WITH MINOR GAPS
