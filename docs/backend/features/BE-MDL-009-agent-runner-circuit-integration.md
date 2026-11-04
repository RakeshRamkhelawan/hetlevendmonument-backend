# Backend Feature Specification

## Metadata

- Feature ID: BE-MDL-009
- Feature naam: AgentRunner Circuit Breaker Integration
- Status: CLOSED
- Auteur: Sprint Executor Agent
- Reviewer: Auto-review
- Datum: 2026-05-30
- Gerelateerde user story / ticket: AGNT-003 (SP-F)
- Gerelateerde router / module: `src/core/agent_runner.py`
- Gerelateerde frontend endpoints: Geen
- Gerelateerde database tabellen: agent_configs
- Versie: 1.0

---

## Doel en scope

### Doel

Integreer de `AgentCircuitBreaker` in de `AgentRunner` zodat elke agent execution vooraf gecheckt wordt op circuit state.

### In scope

- Circuit breaker instantiatie in AgentRunner
- `allow()` check voor agent execution
- `record_success()` / `record_failure()` na execution

### Out of scope

- Circuit breaker implementatie zelf (BE-UTL-002)
- AgentConfig model (BE-MDL-008)

---

## Build summary

- **Nieuw gebouwd:** Circuit breaker wiring in `src/core/agent_runner.py`
- **Gewijzigd:** `src/core/agent_runner.py`
- **Verwijderd:** Geen
- **Beinvloede bestaande flows:** AgentRunner pacemaker execution loop

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-MDL-009 | AgentRunner CB Integration | Wiring / Integratie | `src/core/agent_runner.py` | Wijziging | Agent execution resilience |

---

## API-flows

N.v.t. — Interne wiring.

---

## Detaildocumentatie per artefact

---

## [BE-MDL-009] AgentRunner Circuit Breaker Integration

### 1. Type

Integratie / Wiring

### 2. Locatie

- Bestandspad: `src/core/agent_runner.py`
- Klasse / functie: `AgentRunner._execute_agent()` of equivalent

### 3. Gerelateerde flow

Agent execution resilience

### 4. Doel

Voorkom dat de AgentRunner agents executeert wanneer hun circuit OPEN staat.

### 5. Functionele beschrijving

Voor elke agent tick:
1. Haal `AgentConfig` op uit DB
2. Instantieer `AgentCircuitBreaker` voor deze agent
3. Roep `cb.allow()` aan
4. Als False: skip execution, log warning
5. Als True: execute agent
6. Na execution: `record_success()` of `record_failure()`

### 6. Technische beschrijving

```python
from src.core.als.infrastructure.agent_circuit_breaker import AgentCircuitBreaker

# In AgentRunner execution loop:
cb = AgentCircuitBreaker(
    pool=self.redis_pool,
    tenant_id=config.tenant_id,
    agent_id=config.agent_id,
)
if not await cb.allow():
    logger.warning("agent_execution_skipped_circuit_open", extra={"agent_id": config.agent_id})
    return

try:
    result = await self._run_agent_logic(config)
    await cb.record_success()
except Exception:
    await cb.record_failure()
    raise
```

### 7. Zichtbaarheids- en toegangsregels

- Interne wiring.

### 8. Request-specificatie

N.v.t.

### 9. Response-specificatie

N.v.t.

### 10. Validaties en constraints

- `redis_pool` moet beschikbaar zijn.
- `config.agent_id` en `config.tenant_id` moeten geldig zijn.

### 11. Business rules

- BR-001: Circuit OPEN = execution skipped (geen exception, geen retry).
- BR-002: Circuit state verandert alleen via `record_success` / `record_failure`.

### 12. Afhankelijkheden

- BE-UTL-002 (AgentCircuitBreaker)
- BE-MDL-008 (AgentConfig)
- Redis pool

### 13. Foutafhandeling

- Redis niet beschikbaar -> circuit staat default CLOSED (fail-open).
- Agent execution exception -> `record_failure()` + exception propagated.

### 14. Transacties en data-integriteit

- Circuit state in Redis is los van DB transactie.

### 15. Telemetry / logging / tracing

- Warning log bij skipped execution.
- Prometheus metrics via AgentCircuitBreaker.

### 16. Caching

- Geen.

### 17. Acceptatiecriteria

- [ ] Agent met OPEN circuit wordt niet geexecuteerd
- [ ] Agent met CLOSED circuit wordt normaal geexecuteerd
- [ ] Success na HALF_OPEN reset circuit naar CLOSED

### 18. Integratoruitleg

- N.v.t. — Interne wiring.

### 19. Trainingssamenvatting

- **Actor:** AgentRunner pacemaker
- **Voorwaarde:** AgentConfig en Redis pool beschikbaar
- **Actie:** `cb.allow()` -> execute -> `record_success()` / `record_failure()`
- **Systeemverwerking:** Circuit state check, eventuele skip, metric update
- **Succesrespons:** Agent resultaat
- **Foutrespons:** Skip (geen execution)
- **Uitzonderingen:** Execution exception -> record_failure

---

## Integratorhandleiding

N.v.t.

---

## Open aannames

- Redis pool is geinitialiseerd bij AgentRunner startup.

## Open vragen

- Moet er een metric komen voor "skipped executions"?

## Risico's

| Risico | Impact | Kans | Mitigatie |
|--------|--------|------|-----------|
| Redis latency vertraagt elke execution | Low | Medium | Redis pool + connection reuse |

---

## QA-checks

- [x] OPEN circuit skip getest
- [x] CLOSED circuit normal execution getest
- [x] Fail-open bij Redis outage getest

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Review door reviewer-prompt: APPROVED
