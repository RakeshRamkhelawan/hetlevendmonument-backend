# BE-UTL-039: ProviderRegistry Lazy Discovery

## Samenvatting

Verwijdert module-level auto-discovery uit `ProviderRegistry`. Discovery wordt nu pas getriggerd bij eerste `get()` of `list_providers()` call. Dit bespaart ~1-3s startup tijd.

## Scope

- `src/core/llm/provider_registry.py`

## Wijzigingen

- Regel 92: verwijderd `ProviderRegistry.auto_discover()` bij import
- `get()` en `list_providers()` hadden al lazy check via `_initialized` flag
- Idempotentie: `auto_discover()` retourneert direct als `_initialized` True is

## Tests

- `tests/unit/llm/test_provider_registry_lazy.py` — 4 tests (no import discovery, get triggers, list triggers, idempotency)

## ADR Impact

- ADR-009 (Traefik/health): snellere startup

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)

> Vermijd module-level I/O (file scans, imports, network calls). Gebruik lazy initialisatie: eerste functie-call triggert setup. Idempotentie garandeert dat herhaalde calls veilig zijn.
