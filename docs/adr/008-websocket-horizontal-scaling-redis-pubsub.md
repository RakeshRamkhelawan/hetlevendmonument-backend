# ADR-008: WebSocket Horizontal Scaling - Redis Pub/Sub

## Status
Accepted

## Context
WebSockets zijn stateful verbindingen naar één specifieke server-instantie. In een geschaalde omgeving met meerdere backend nodes ontstaat het probleem dat een worker op Node A een update heeft voor een client die verbonden is met Node B.

## Decision
We gebruiken **Redis Pub/Sub** als de backbone voor real-time event distributie.

### 1. Fan-out Architectuur
- Wanneer een event (bijv. een nieuw chatbericht of taak-update) gegenereerd wordt, wordt dit gepubliceerd op een Redis kanaal gescoped per tenant: `tenant:{tenant_id}:events`.
- Elke backend node luistert naar dit kanaal en stuurt het bericht door naar alle lokaal verbonden clients van die specifieke tenant.

### 2. Event Berichtenstructuur
```json
{
  "type": "TASK_UPDATED",
  "data": {
    "task_id": "...",
    "new_status": "COMPLETED"
  },
  "tenant_id": "..."
}
```

### 3. Schaalbaarheidslimieten (SLO)
| Metriek | Target | Doel |
| :--- | :--- | :--- |
| **Broadcast Latency** | < 50ms | Vertraging tussen Nodes |
| **Max Connections** | 10k per Node | Voorkom FD (File Descriptor) exhaustion |
| **Message Ordering** | FIFO per Tenant | Voorkom out-of-order chat berichten |

## Consequences
- **Positive**:
    - Volledig horizontaal schaalbaar: Meer gebruikers = meer backend nodes toevoegen zonder architecturale wijzigingen.
    - Ontkoppeling: Workers hoeven niet te weten waar clients zich bevinden; ze publiceren simpelweg naar Redis.
- **Negative**:
    - Single Point of Failure: Als Redis uitval, stoppen alle real-time updates (fallback naar polling vereist, zie ADR-007).
    - Extra bandbreedte consumptie tussen Nodes in een zeer druk systeem.
- **Notes**:
    - We gebruiken `redis-py` met de `pubsub()` module voor de implementatie in de real-time service.
    - Sticky sessions op de load balancer (Traefik) zijn *niet* vereist, maar kunnen helpen bij het stabiliseren van de verbinding.

---

## Implementatie-bevindingen -- Architectuur Audit 2026-05-31

### WE-012 [CRITICAL] WSPusher subscriber-kant ontbreekt -- alle proactieve notificaties worden weggegooid

**Situatie:** ADR-008 beschrijft een volledige Redis pub/sub naar WebSocket broadcast pipeline.
**Werkelijkheid:** `WSPusher` publiceert naar Redis kanaal `ws:user:{user_id}`, maar geen enkele code
abonneert op dit kanaal en stuurt berichten door naar browser WebSocket clients.
`ws_pusher.py` docstring regel 6 staat letterlijk: *"subscriber side lives in the WS endpoint
(sprint 6 dependency)"*. `ConnectionManager` (`src/core/websocket/manager.py` regels 54-306)
heeft geen Redis-client veld en geen `subscribe()` methode.
Alle proactieve notificaties worden via `best_effort()` stil weggegooid.
**Bewijs:** `src/core/copilot/notification/ws_pusher.py:6`, grep op `ws:user` geeft alleen
`ws_pusher.py` terug. `src/core/websocket/manager.py:54-306` (geen Redis veld of subscribe methode).
**Impact:** Sprint 5 produceerde 10 proactieve monitors + NotificationDispatcher. Geen enkel signaal
bereikt de browser. De volledige proactieve monitoring UI is non-functioneel.
**Sprint:** SP-WE-02

### WE-013 [HIGH] /ws/copilot/signals endpoint bestaat niet

**Situatie:** Frontend `useProactiveSignals` hook verbindt met `/ws/copilot/signals`.
**Werkelijkheid:** `src/core/api/copilot_websocket_endpoints.py` definieert uitsluitend
`/ws/copilot/stats`. Het pad `/ws/copilot/signals` is nooit geregistreerd.
Elke verbindingspoging van de frontend geeft 404/connection refused.
**Bewijs:** `src/core/api/copilot_websocket_endpoints.py` (alleen `/ws/copilot/stats`),
`frontend/src/hooks/useProactiveSignals.ts` (verbindt met `/ws/copilot/signals`).
**Impact:** Alle proactieve UI-signalen (agent health, budget warnings, compliance alerts)
zijn afwezig in de productie-UI.
**Sprint:** SP-WE-02

## Changelog

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | 2026-05-10 | Initial decision -- Redis pub/sub voor WebSocket horizontal scaling |
| **1.1** | **2026-05-31** | **WE-012/013 gedocumenteerd: WSPusher subscriber ontbreekt, /ws/copilot/signals endpoint bestaat niet. Fix in SP-WE-02.** |
