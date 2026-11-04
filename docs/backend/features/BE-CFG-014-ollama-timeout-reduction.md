# BE-CFG-014: Ollama Timeout Reduction

## Samenvatting

Vermindert de Ollama connectie-timeout van 5 seconden naar 1 seconde in alle Ollama-gerelateerde componenten. Dit bespaart ~4s per startup wanneer Ollama niet draait (standaard in dev).

## Scope

- `src/core/llm/ollama_provider.py` — `initialize()` en `health_check()`
- `src/core/llm/ollama_client.py` — `health_check()` en `_initialize()`

## Wijzigingen

| Bestand | Regel | Van | Naar |
|---------|-------|-----|------|
| `ollama_provider.py` | 66 | `ClientTimeout(total=5)` | `ClientTimeout(total=1)` |
| `ollama_provider.py` | 308 | `ClientTimeout(total=5)` | `ClientTimeout(total=1)` |
| `ollama_client.py` | 105 | `ClientTimeout(total=5)` | `ClientTimeout(total=1)` |
| `ollama_client.py` | 158 | `ClientTimeout(total=5)` | `ClientTimeout(total=1)` |

## Tests

- `tests/unit/test_startup_ollama_timeout.py` — 3 tests (provider timeout, client timeout, unreachable quick-fail)

## ADR Impact

- ADR-009 (Traefik/health): snellere startup = betrouwbaardere health checks

## Trainingssamenvatting

> Bij het initialiseren van optionele externe services (Ollama), gebruik een korte timeout (1s) zodat fallback snel wordt geactiveerd. Een 5s timeout blokkeert de hele startup pipeline onnodig.

- Actor: interne component (niet direct gebruikersgericht)
- Voorwaarde: systeem operationeel; afhankelijkheden beschikbaar
- Actie: automatisch bij startup of deployment
- Systeemverwerking: zie technische beschrijving in spec
- Succesrespons: component actief en beschikbaar
- Foutrespons: startup of initialisatie mislukt; zie applicatielogs
- Uitzonderingen: n.v.t.
