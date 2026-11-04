# BE-UTL-033 -- LLMHandler Multi-Provider Failover (SP-WE-07)

**ID:** BE-UTL-033
**Sprint:** SP-WE-07
**Datum:** 2026-06-01
**ADR:** ADR-026, ADR-027 (WE-006)

---

## Samenvatting

`LLMHandler` gebruikte een single `LLMClient` provider zonder failover (WE-006). Bij
provider-failure: directe `LLMProviderError` zonder backup. Nu ondersteunt `LLMHandler`
meerdere providers met per-provider `CircuitBreakerRegistry`.

**Architectuurnoot:** `LLMFallbackChain` (src/core/llm/fallback_chain.py) gebruikt
`prompt: str` (tekst-generatie) en is incompatibel met `LLMClient.complete_json(messages, schema)`.
De copilot-turn vereist gestructureerde JSON-output via `complete_json()`. Failover is
daarom direct in `LLMHandler` geimplementeerd via de bestaande `CircuitBreakerRegistry`.

## Wijzigingen

| Bestand | Wijziging |
| --- | --- |
| `src/core/copilot/llm_handler.py` | `LLMProviderError` class; `fallback_providers: list[LLMClient]` + `circuit_breaker_registry` constructor params; `_call_provider()` helper met `cb.execute()`; `get_action()` iterates over providers + circuit-open skip |
| `src/core/copilot/dependencies.py` | `CircuitBreakerRegistry()` aangemaakt en doorgegeven aan `LLMHandler` |

## Failover patroon

```
get_action() iterates: [primary] + fallback_providers
  for each provider:
    cb_key = "{ProviderClass}#{model_id}"
    cb.execute(prov.complete_json) -- CircuitOpenError -> skip
    if not raw.success: LLMProviderError -> continue
    CopilotAction.model_validate_json(raw.content)
    ValidationError -> retry once -> next provider
After all exhausted: raise last_error
```

## SP-H03 guard herstel

De `raw.success` guard (SP-H03) was afwezig in de originele `get_action()`. Nu
aanwezig in `_call_provider()` voor zowel de eerste aanroep als de retry.

## Trainingssamenvatting

### Flow 1: LLM failover bij provider outage

- **Actor:** LLMHandler.get_action() (systeem)
- **Voorwaarde:** PRIMARY LLM provider retourneert `raw.success=False` of `CircuitOpenError`
- **Actie:** `_call_provider()` verhoogt circuit breaker failure count; loop `continue` naar volgende provider
- **Systeemreactie:** `CircuitBreakerRegistry` checkt provider state; open circuit (`CircuitOpenError`) -> skip zonder failure count
- **Succesrespons:** Fallback provider retourneert `raw.success=True`; `CopilotAction` geretourneerd
- **Foutrespons:** Alle providers gefaald -> `LLMProviderError` raised -> `CopilotService._blocked_response()`
- **Uitzonderingen:** Geen fallback providers geconfigureerd -> gedraagt zich als single-provider (backward compat)
