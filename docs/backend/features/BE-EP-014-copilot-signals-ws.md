# Backend Feature Specification

## Metadata

- Feature ID: BE-EP-014
- Feature naam: /ws/copilot/signals Real-time signals WebSocket endpoint
- Status: READY
- Auteur: Antigravity AI
- Reviewer: code-reviewer, quality-reviewer
- Datum: 2026-05-31
- Gerelateerde user story / ticket: SP-WE-02 Dag 2 (WE-012/013/014)
- Gerelateerde router / module: `src/core/api/copilot_websocket_endpoints.py`
- Gerelateerde frontend endpoints: `/ws/copilot/signals`
- Gerelateerde database tabellen: N/A
- Versie: 1.0

---

## Doel en scope

### Doel

Bieden van een real-time WebSocket-kanaal voor proactieve signalen (gegenereerd door de Sprint 5 monitors). Dit stelt de frontend (`useProactiveSignals` hook) in staat om direct events te ontvangen via de Redis-subscriber `ConnectionManager` zonder polling.

### In scope

- WebSocket handshake op `/ws/copilot/signals`
- Authenticatie via JWT cookie-first (`access_token`) of fallback `?token=` query parameter
- Registratie van WebSocket in `ConnectionManager` (Redis Pub/Sub wrapper)
- Automatische cleanup bij disconnect of exception (unsubscribe en task-cancel)

### Out of scope

- Direct chatten over dit specifieke WebSocket kanaal (hiervoor is `/ws/copilot/chat`)

---

## Build summary

- Nieuw gebouwd:
  - WebSocket `/ws/copilot/signals` endpoint in [copilot_websocket_endpoints.py](file:///C:/Users/rsram/OneDrive/Documenten/GitHub/SanskritiSetu.org/src/core/api/copilot_websocket_endpoints.py)
  - Unit tests in [test_sp_we_02_ws_signals_endpoint.py](file:///C:/Users/rsram/OneDrive/Documenten/GitHub/SanskritiSetu.org/tests/unit/test_sp_we_02_ws_signals_endpoint.py)
- Gewijzigd:
  - `ConnectionManager` in [manager.py](file:///C:/Users/rsram/OneDrive/Documenten/GitHub/SanskritiSetu.org/src/core/websocket/manager.py) (Redis pub/sub subscriber, cleanup en async listener task logic)
- Verwijderd:
  - N/A
- Beïnvloede bestaande flows:
  - `WSPusher.push()` signalen worden nu echt doorgestuurd naar de browser.

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-EP-014 | `/ws/copilot/signals` | WebSocket Endpoint | `src/core/api/copilot_websocket_endpoints.py` | Nieuw | BE-FLW-003 |

---

## API-flows

### Flow ID: BE-FLW-003

- Naam: Proactieve monitor signalering via WebSocket
- Trigger (HTTP-methode + route of event): WebSocket connectie op `/ws/copilot/signals` en daarna Redis pub/sub event op `ws:user:{user_id}`
- Voorwaarden (auth, tenant, feature flag): Geldig JWT access token (cookie of query param)
- Request-pad: Browser -> `/ws/copilot/signals` -> `ConnectionManager.subscribe_user`
- Service-stappen:
  1. Handshake en extractie van `current_user` en `tenant_id`
  2. Aanmelden WebSocket bij `ConnectionManager`
  3. Starten van een `asyncio.Task` voor de Redis subscriber `_redis_listener` op kanaal `ws:user:{user_id}`
  4. Bij een inkomend Redis-bericht: forwarden naar de WebSocket
- DB-operaties: N/A
- Successtatus + response: WebSocket verbinding geaccepteerd, houdt open.
- Foutpaden:
  - Ongeldige JWT: direct sluiten met WS_1008_POLICY_VIOLATION
  - WebSocket closed/broken: `disconnect` handler ruimt Redis-subscriber en tasks op.
- Eindtoestand (DB, cache, events): Verbinding gesloten en opgeruimd.

---

## Detaildocumentatie per artefact

## [BE-EP-014] /ws/copilot/signals

### 1. Type

- WebSocket Endpoint

### 2. Locatie

- Bestandspad: `src/core/api/copilot_websocket_endpoints.py`
- Klasse / functie: `copilot_signals_websocket`

### 3. Gerelateerde flow

- BE-FLW-003

### 4. Doel

- Real-time notificatie en proactieve signaaldoorgifte naar de frontend client.

### 5. Functionele beschrijving

- Het endpoint accepteert WebSocket connecties van ingelogde gebruikers en filtert de events specifiek op hun `user_id`. Het maakt gebruik van een Redis Pub/Sub kanaal om real-time events door te sturen.

### 6. Technische beschrijving

- Maakt gebruik van FastAPI's `@router.websocket` decorator.
- Verkrijgt de `current_user` via `get_current_user_ws` dependency.
- Verkrijgt `ConnectionManager` via FastAPI dependency injection of app state.
- Loopt over `websocket.receive_text()` in een `while True` loop om de verbinding open te houden en disconnecties te detecteren.

### 7. Zichtbaarheids- en toegangsregels

- Vereiste authenticatie: Ja, JWT token.
- Vereiste rol / scope: Geldige user rol.
- Tenant-isolatie: Ja, events zijn per user en tenant gesegmenteerd.
- Feature flag: N/A

### 8. Request-specificatie

- Methode: WS
- Route: `/ws/copilot/signals`
- Path parameters: N/A
- Query parameters: `token` (optionele fallback)
- Request body (schema): N/A
- Verplichte headers: `Cookie` (bevattende `access_token`) of `Authorization: Bearer` (voor HTTP client mocks).

### 9. Response-specificatie

- Successtatus: 101 Switching Protocols
- Response schema: N/A (Websocket frame payload: JSON strings)
- Foutstatussen: 401 Unauthorized (gesloten met status code 1008)

### 10. Validaties en constraints

- JWT token moet valide zijn en een `user_id` bevatten.

### 11. Business rules

- Redis kanaal: `ws:user:{user_id}`.
- Maximaal 1 listener task per actieve user op de worker (hergebruikt verbindingen).

### 12. Afhankelijkheden

- `ConnectionManager`, Redis service.

### 13. Foutafhandeling

- WS disconnecties worden afgevangen (`WebSocketDisconnect`) waarna `ConnectionManager.disconnect` wordt aangeroepen.

### 14. Transacties en dataïntegriteit

- N/A

### 15. Telemetry / logging / tracing

- Logt WS connections en disconnections.

### 16. Caching

- Gecached: Nee
- Cache-sleutel: N/A

### 17. Acceptatiecriteria

- [x] WebSocket handshake slaagt met geldige JWT token.
- [x] WebSocket verbinding wordt geweigerd zonder token.
- [x] Redis Pub/Sub berichten worden correct doorgestuurd.
- [x] Geen geheugenlekken (tasks en subscribers worden opgeruimd bij disconnect).

### 18. Integratoruitleg

- Maak verbinding met `wss://<host>/ws/copilot/signals` met de `access_token` cookie ingesteld.
- Ontvang JSON signalen met monitor metadata in real-time.

### 19. Trainingssamenvatting

- Actor: Frontend client (`useProactiveSignals`)
- Voorwaarde: Ingelogde gebruiker
- Actie (request): WS connect `/ws/copilot/signals`
- Systeemverwerking: Authenticeert, opent Redis listener task
- Succesrespons: Verbinding open, real-time events worden gepusht
- Foutrespons: 1008 Policy Violation (indien unauthenticated)
- Uitzonderingen: Redis verbroken -> logt fout, pusher faalt stil.

---

## Open aannames

- Er is een actieve Redis container aanwezig om pub/sub te verwerken.

## Open vragen

- Geen.

## Risico's

- Hoge concurrency aan WebSocket connecties kan leiden tot veel async Redis listener tasks. Dit is gemitigeerd door task cancellation en mapping per user_id.

---

## QA-checks

- [x] Endpoint functioneel getest (happy path)
- [x] Alle foutstatus-codes getest
- [x] Auth en permissies getest
- [x] Tenant-isolatie getest
- [x] Validaties getest (ongeldige invoer)
- [x] Edge cases getest (leeg, null, grenzen)
- [x] Dataïntegriteit en transacties getest
- [x] Logging en tracing gecontroleerd

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle endpoints, services en modellen zijn geïnventariseerd
- [x] Alle relevante foutstatussen zijn beschreven
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg is aanwezig
- [x] Trainingssamenvatting is aanwezig
- [x] Open aannames zijn benoemd
- [x] QA-checks zijn uitgevoerd
- [x] Review door reviewer-prompt: APPROVED
