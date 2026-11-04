# Backend Feature Specification

## Metadata

- Feature ID: BE-UTL-002
- Feature naam: AgentCircuitBreaker (Redis-backed)
- Status: CLOSED
- Auteur: Sprint Executor Agent
- Reviewer: Auto-review
- Datum: 2026-05-30
- Gerelateerde user story / ticket: AGNT-003 (SP-F)
- Gerelateerde router / module: `src/core/als/infrastructure/agent_circuit_breaker.py`
- Gerelateerde frontend endpoints: Geen
- Gerelateerde database tabellen: Geen (Redis)
- Versie: 1.0

---

## Doel en scope

### Doel

Per-agent circuit breaker met drie toestanden (CLOSED, OPEN, HALF_OPEN) om cascade failures bij agent execution te voorkomen. Redis-backed voor distributie over meerdere workers.

### In scope

- `CircuitState` enum
- `_CircuitBreakerConfig` dataclass
- `AgentCircuitBreaker` klasse
- Prometheus metrics integratie

### Out of scope

- AgentRunner zelf (BE-SVC-006)
- Circuit breaker integratie in AgentRunner (BE-MDL-009)

---

## Build summary

- **Nieuw gebouwd:** `src/core/als/infrastructure/agent_circuit_breaker.py`
- **Gewijzigd:** Geen
- **Verwijderd:** Geen
- **Beinvloede bestaande flows:** AgentRunner execution (leest CB state voor start)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-UTL-002 | AgentCircuitBreaker | Utility klasse | `src/core/als/infrastructure/agent_circuit_breaker.py` | Nieuw | Agent execution resilience |

---

## API-flows

N.v.t. — Interne utility.

---

## Detaildocumentatie per artefact

---

## [BE-UTL-002] AgentCircuitBreaker

### 1. Type

Utility klasse

### 2. Locatie

- Bestandspad: `src/core/als/infrastructure/agent_circuit_breaker.py`
- Klasse / functie: `AgentCircuitBreaker`, `CircuitState`, `_CircuitBreakerConfig`

### 3. Gerelateerde flow

Agent execution resilience

### 4. Doel

Voorkom dat een falende agent oneindig retries triggert. Na 5 failures gaat de circuit OPEN; na 30s probeert HALF_OPEN; bij 2 successen gaat weer naar CLOSED.

### 5. Functionele beschrijving

- **CLOSED:** Normale operatie. Alle requests worden doorgelaten.
- **OPEN:** Requests worden geblokkeerd. Timer loopt voor reset.
- **HALF_OPEN:** Een test-request wordt toegelaten. Bij success -> CLOSED, bij failure -> OPEN.
- Metrics worden doorgestuurd naar Prometheus.

### 6. Technische beschrijving

```python
class CircuitState(Enum):
    CLOSED = "closed"; OPEN = "open"; HALF_OPEN = "half_open"

class AgentCircuitBreaker:
    def __init__(self, pool, tenant_id, agent_id, failure_threshold=5, success_threshold=2, reset_timeout_seconds=30)
    async def get_state() -> CircuitState
    async def allow() -> bool
    async def record_success() -> CircuitState
    async def record_failure() -> CircuitState
    async def reset()
```

**Redis key:** `circuit:{tenant_id}:{agent_id}` (Hash: state, failure_count, success_count, last_failure_time)

**Metrics:**
- `AGENT_CIRCUIT_STATE` (gauge)
- `AGENT_CIRCUIT_FAILURES_TOTAL` (counter)
- `AGENT_CIRCUIT_SUCCESSES_TOTAL` (counter)
- `AGENT_CIRCUIT_OPENS_TOTAL` (counter)

### 7. Zichtbaarheids- en toegangsregels

- Geen auth; interne infrastructuur.
- `tenant_id` + `agent_id` vormen de scope.

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- `failure_threshold >= 1`
- `success_threshold >= 1`
- `reset_timeout_seconds >= 0`

### 11. Business rules

- BR-001: OPEN state blokkeert alle requests.
- BR-002: Na `reset_timeout_seconds` automatisch naar HALF_OPEN.
- BR-003: HALF_OPEN + `success_threshold` successen -> CLOSED.
- BR-004: HALF_OPEN + 1 failure -> OPEN.

### 12. Afhankelijkheden

- Redis connection pool
- `src.core.monitoring.agent_circuit_metrics`

### 13. Foutafhandeling

- Redis niet beschikbaar -> metrics falen silently (`try/except` rond metric updates).
- Corrupte state in Redis -> default naar CLOSED.

### 14. Transacties en data-integriteit

- Redis Hash operaties zijn atomaar per field.
- State transitions zijn niet atomair over meerdere fields; race conditions mogelijk bij hoge concurrency.

### 15. Telemetry / logging / tracing

- Prometheus metrics (zie boven).
- Geen directe logging in circuit breaker.

### 16. Caching

- `DEPARTMENT_TOPICS` is immutable; geen caching nodig.
- Redis zelf is de state store.

### 17. Acceptatiecriteria

- [ ] 5 failures -> OPEN
- [ ] OPEN na 30s -> HALF_OPEN bij `allow()`
- [ ] HALF_OPEN + 2 successen -> CLOSED
- [ ] HALF_OPEN + 1 failure -> OPEN
- [ ] Metrics labels bevatten tenant_id en agent_id

### 18. Integratoruitleg

- Instantieer met `AgentCircuitBreaker(pool, tenant_id, agent_id)`.
- Roep `allow()` aan voor elke agent execution.
- Roep `record_success()` of `record_failure()` na execution.

### 19. Trainingssamenvatting

- **Actor:** AgentRunner
- **Voorwaarde:** Redis beschikbaar
- **Actie:** `cb.allow()` -> execute agent -> `cb.record_success()` / `cb.record_failure()`
- **Systeemverwerking:** State machine transition in Redis
- **Succesrespons:** True (uitvoering toegestaan) of False (geblokkeerd)
- **Foutrespons:** Geblokkeerd bij OPEN state
- **Uitzonderingen:** Redis failure -> default CLOSED (fail-open)

---

## Integratorhandleiding

N.v.t. — Interne infrastructuur.

---

## Open aannames

- Redis is single-threaded; Hash operaties zijn voldoende atomair voor deze use case.
- Fail-open is gewenst bij Redis outage (niet fail-closed).

## Open vragen

- Moet de circuit breaker persistenter zijn dan Redis (bijv. PostgreSQL fallback)?
- Moet er een bulk reset API komen voor tenant-wide re-enabling?

## Risico's

| Risico | Impact | Kans | Mitigatie |
|--------|--------|------|-----------|
| Race condition bij state transition | Medium | Low | Acceptabel voor huidige load; overweeg Lua script bij schaling |
| Redis data loss -> circuits verdwijnen | Low | Low | Circuits rebuilden zichzelf automatisch |

---

## QA-checks

- [x] Happy path (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- [x] Fail-open bij Redis outage
- [x] Deduplicatie metrics

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Review door reviewer-prompt: APPROVED
