# Backend Feature Specification

## Metadata

- Feature ID: BE-UTL-006
- Feature naam: CircuitBreakerRegistry per LLM provider (B-008 fix)
- Status: APPROVED
- Auteur: Claude Sonnet 4.6
- Reviewer: code-reviewer + quality-reviewer subagents (Laag A/C)
- Datum: 2026-05-30
- Gerelateerde user story / ticket: MASTER-AUDIT-COMPLEET.md B-008
- Gerelateerde router / module: src/core/llm/fallback_chain.py
- Gerelateerde frontend endpoints: geen (interne LLM infrastructuur)
- Gerelateerde database tabellen: geen
- Versie: 1.0

---

## Doel en scope

### Doel

LLMFallbackChain had geen circuit breaker. Bij provider outage probeert de chain
de dode provider bij elke call opnieuw, wat vertraging veroorzaakt (wacht op timeout)
en cascade failure kan triggeren. Fix: CircuitBreakerRegistry per provider+model
ingebreid in LLMFallbackChain.generate() (ADR-026, B-008).

### In scope

- CircuitBreakerRegistry ingebreid in LLMFallbackChain
- CB-key: {provider}#{model_name} per unieke combinatie
- CircuitOpenError -> skip zonder attempts te verhogen (fallback budget gespaard)
- get_circuit_states() methode voor monitoring
- CircuitBreakerRegistry aan __all__ in circuit_breaker.py

### Out of scope

- Prometheus metrics voor circuit state changes (post-MVP)
- Shared registry tussen meerdere LLMFallbackChain instanties
- Redis-backed circuit breaker (in-memory volstaat voor single-process)

---

## Build summary

- Gewijzigd: src/core/llm/fallback_chain.py (import + _cb_registry + generate wrapper + get_circuit_states)
- Gewijzigd: src/core/resilience/circuit_breaker.py (CircuitBreakerRegistry aan __all__)
- Nieuw: tests/unit/test_sp_h05_llm_circuit_breaker.py (7 tests)

---

## Backend inventory

| ID | Naam | Type | Bestandspad | Nieuw/Wijziging | Gerelateerde flow |
| --- | --- | --- | --- | --- | --- |
| BE-UTL-006a | LLMFallbackChain circuit breaker integratie | Utility fix | src/core/llm/fallback_chain.py | Wijziging | LLM failover flow |
| BE-UTL-004b | LLMFallbackChain.get_circuit_states() | Method (nieuw) | src/core/llm/fallback_chain.py | Nieuw | LLM monitoring flow |

---

## API-flows

### Flow 1: LLM failover met circuit breaker

- Naam: LLM call met circuit breaker skip
- Trigger: await chain.generate(prompt=...)
- Voorwaarden: een of meer providers mogelijk in OPEN state
- Request-pad: caller -> LLMFallbackChain.generate() -> per model: cb.execute(_call_model)
- Service-stappen:
  1. Loop over ModelTier (PRIMARY -> SECONDARY -> LOCAL -> HEURISTIC)
  2. Per model: cb_key = f"{provider}#{name}", cb = await registry.get_breaker(cb_key)
  3. result = await cb.execute(self._call_model, model_config=..., ...)
  4. Bij CircuitOpenError: logger.info + continue (attempts NIET verhoogd)
  5. Bij succes: attempts += 1, return FallbackResult
  6. Bij TimeoutError/Exception: attempts += 1, errors.append, volgende model
- DB-operaties: geen
- Successtatus: FallbackResult(success=True, model_used=..., attempts=N)
- Foutpaden:
  - Alle providers OPEN: FallbackResult(success=False, attempts=0)
  - Alle providers falen: FallbackResult(success=False, attempts=N, errors=[...])
- Eindtoestand: circuit breakers bijgewerkt per provider (failure count, state)

### Flow 2: Circuit state monitoring

- Naam: Circuit state opvragen
- Trigger: await chain.get_circuit_states()
- Voorwaarden: LLMFallbackChain instantie actief
- Service-stappen: await self._cb_registry.get_all_states()
- Successtatus: dict met per-provider state + metrics
- Eindtoestand: read-only

---

## Detaildocumentatie per artefact

---

## [BE-UTL-006a] LLMFallbackChain circuit breaker integratie

### 1. Type
- Utility fix (resilience pattern)

### 2. Locatie
- Bestandspad: src/core/llm/fallback_chain.py
- Klasse / functie: LLMFallbackChain.__init__, LLMFallbackChain.generate

### 3. Gerelateerde flow
- LLM failover flow

### 4. Doel
Beschermt de failover chain tegen cascade failure bij LLM provider outage.
OPEN providers worden overgeslagen zonder de fallback budget te consumeren.

### 5. Functionele beschrijving
Na 3 opeenvolgende failures gaat een provider circuit OPEN. Gedurende 60 seconden worden
calls naar die provider direct als CircuitOpenError teruggegeven en overgeslagen.
Na 60 seconden gaat het circuit naar HALF_OPEN en wordt 1 probe request toegestaan.
Bij succes: terug naar CLOSED. Bij failure: weer OPEN.

### 6. Technische beschrijving
Import: CircuitBreakerRegistry, CircuitOpenError from src.core.resilience.circuit_breaker.
In __init__: self._cb_registry = CircuitBreakerRegistry() (per-instance).
In generate() loop: cb_key = f"{model_config.provider}#{model_config.name}",
cb = await self._cb_registry.get_breaker(cb_key, failure_threshold=3, recovery_timeout=60.0),
result = await cb.execute(self._call_model, model_config=..., ...).
CircuitOpenError: logger.info + continue. Succes/Timeout/Exception: attempts += 1.

### 7. Zichtbaarheids- en toegangsregels
- Intern gebruik (geen HTTP endpoint)
- Geen tenant-isolatie (LLM infra is platform-breed)

### 8. Request-specificatie
- Handtekening: ongewijzigd (backward compatible)
- async def generate(self, prompt, system_prompt, response_model, temperature, max_tokens, fallback, preferred_tier, timeout) -> FallbackResult

### 9. Response-specificatie
- FallbackResult(success, content, model_used, tier_used, latency_ms, attempts, errors, ...)
- attempts = echte call-pogingen (circuit-open skips tellen niet mee)

### 10. Validaties en constraints
- failure_threshold=3 (hardcoded)
- recovery_timeout=60s (hardcoded)
- CB-key is ASCII-safe

### 11. Business rules
- CircuitOpenError verhoogt attempts NIET
- Elke LLMFallbackChain instantie heeft eigen registry
- Module-level singleton heeft persistente CB state over calls

### 12. Afhankelijkheden
- src.core.resilience.circuit_breaker.CircuitBreakerRegistry
- src.core.resilience.circuit_breaker.CircuitOpenError

### 13. Foutafhandeling
- CircuitOpenError: logger.info + skip (geen errors.append)
- TimeoutError: attempts += 1, errors.append
- Exception: attempts += 1, errors.append

### 14. Transacties en dataintegiteit
- Geen DB-operaties; alle state is in-memory

### 15. Telemetry / logging / tracing
- logger.info("llm_circuit_open_skipping: %s", cb_key) bij OPEN skip

### 16. Caching
- Niet van toepassing

### 17. Acceptatiecriteria
- CircuitBreakerRegistry aanwezig in fallback_chain.py source
- CircuitOpenError aanwezig in fallback_chain.py source
- LLMFallbackChain() heeft _cb_registry attribuut
- FallbackResult.attempts = 0 als alle providers OPEN
- OPEN skip is niet aanwezig in FallbackResult.errors

### 18. Integratoruitleg
- Transparant voor callers: signature ongewijzigd
- Bij alle providers OPEN: FallbackResult(success=False, attempts=0, errors=[])
- Singleton via get_fallback_chain() heeft persistente CB state

### 19. Trainingssamenvatting

- Actor: LLM-gebruikende services (copilot, agent selector)
- Voorwaarde: provider heeft 3+ opeenvolgende failures gehad (circuit OPEN)
- Actie: await chain.generate(prompt=...)
- Systeemverwerking: cb.execute() raises CircuitOpenError -> skip -> volgende provider
- Succesrespons: FallbackResult(success=True) via een werkende provider
- Foutrespons: FallbackResult(success=False, attempts=0) als alle providers OPEN
- Uitzonderingen: HALF_OPEN -> 1 probe; succes -> CLOSED; failure -> terug naar OPEN

---

## [BE-UTL-006b] LLMFallbackChain.get_circuit_states()

### 1. Type
- Method (monitoring/diagnostics)

### 2. Locatie
- Bestandspad: src/core/llm/fallback_chain.py
- Klasse / functie: LLMFallbackChain.get_circuit_states

### 3. Gerelateerde flow
- LLM monitoring flow

### 4. Doel
Geef huidige circuit breaker states terug voor alle providers die via deze chain zijn aangeroepen.

### 5. Functionele beschrijving
Retourneert een dict met per CB-key (provider#model) de huidige state en metrische data.

### 6. Technische beschrijving
async def get_circuit_states(self) -> dict[str, dict[str, Any]]:
    # NOTE: inner dict mirrors CircuitBreaker.get_state() schema (state, metrics)
    return await self._cb_registry.get_all_states()

### 7. Zichtbaarheids- en toegangsregels
- Intern gebruik; expose via admin endpoint met require_admin guard

### 8. Request-specificatie
- Handtekening: async def get_circuit_states(self) -> dict[str, dict[str, Any]]

### 9. Response-specificatie
- dict[str, dict[str, Any]]: keys zijn CB-keys, values zijn state dicts
- Lege dict bij een verse chain zonder calls

### 10. Validaties en constraints
- Async lock in get_all_states() zorgt voor thread-safe toegang

### 11. Business rules
- Lege dict = nog geen providers ooit geprobeerd (correct, geen fout)

### 12. Afhankelijkheden
- CircuitBreakerRegistry.get_all_states()

### 13. Foutafhandeling
- Geen exceptions verwacht (async lock guard)

### 14. Transacties en dataintegiteit
- Read-only, geen state change

### 15. Telemetry / logging / tracing
- Geen logging in get_circuit_states() zelf

### 16. Caching
- Niet gecached (live state)

### 17. Acceptatiecriteria
- await chain.get_circuit_states() retourneert dict
- Lege dict bij verse chain

### 18. Integratoruitleg
- Admin monitoring: states = await chain.get_circuit_states()
- open_providers = [k for k, v in states.items() if v.get("state") == "open"]

### 19. Trainingssamenvatting

- Actor: admin systeem of monitoring
- Voorwaarde: LLMFallbackChain instantie actief
- Actie: states = await chain.get_circuit_states()
- Systeemverwerking: CircuitBreakerRegistry.get_all_states() met async lock
- Succesrespons: dict met per-provider state en metrics
- Foutrespons: lege dict bij geen geregistreerde breakers
- Uitzonderingen: geen

---

## Integratorhandleiding

### Voor callers van generate()

Geen code wijzigingen nodig: signature ongewijzigd. Circuit breakers werken transparant.
Bij alle providers OPEN: FallbackResult.success=False, attempts=0.

### Voor monitoring

```python
from src.core.llm.fallback_chain import get_fallback_chain
chain = get_fallback_chain()
states = await chain.get_circuit_states()
open_providers = [k for k, v in states.items() if v.get("state") == "open"]
```

---

## Open aannames

- failure_threshold=3 en recovery_timeout=60s zijn hardcoded; configureerbaar is post-MVP
- moonshot provider is geregistreerd in get_fallback_chain() maar heeft geen _call_model branch
  (pre-existing: 3 failures -> circuit OPEN -> moonshot stil geskipt -- niet erger dan zonder CB)

## Open vragen

Geen

## Risico's

- Per-instance registry: twee LLMFallbackChain instanties delen geen circuit state
  (alleen relevant bij niet-singleton gebruik)

---

## QA-checks

- [x] CircuitBreakerRegistry import aanwezig in fallback_chain.py
- [x] _cb_registry attribuut aanwezig
- [x] get_circuit_states() methode aanwezig
- [x] OPEN skip verhoogt attempts niet
- [x] 7/7 SP-H05 unit tests PASS

---

## Definition of Done

- [x] Feature is gebouwd
- [x] Alle artefacten geinventariseerd
- [x] Functionele beschrijving aanwezig
- [x] Technische beschrijving aanwezig
- [x] Acceptatiecriteria zijn testbaar
- [x] Integratoruitleg aanwezig
- [x] Trainingssamenvatting aanwezig per artefact (BE-UTL-004a + BE-UTL-004b)
- [x] Review: zie docs/backend/review/review-BE-UTL-006.md
