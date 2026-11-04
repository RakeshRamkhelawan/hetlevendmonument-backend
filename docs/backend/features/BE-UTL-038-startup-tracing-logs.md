# BE-UTL-038: Startup Tracing Logs

## Samenvatting

Voegt timing logs toe aan elke initialisatiefase in `app_lifespan.py`. Dit maakt het mogelijk om startup bottlenecks te identificeren zonder externe profilers.

## Scope

- `src/core/app_lifespan.py` — startup fase

## Wijzigingen

1. `import time` toegevoegd
2. `startup_start = time.perf_counter()` aan begin van lifespan
3. Elke `_init_*` stap wordt getimed en gelogd als `[STARTUP] {name} took {duration:.2f}s`
4. Totale startup tijd wordt gelogd als `[OK] Application ready (total startup: {duration:.2f}s)`
5. Gefaalde stappen loggen `[STARTUP] {name} failed after {duration:.2f}s: {exc}`

## Tests

- `tests/unit/test_startup_tracing_logs.py` — 2 tests (happy path timing, failed step logging)

## ADR Impact

- ADR-014 (OpenTelemetry): logs vormen eerste laag van observability

## Trainingssamenvatting

- Actor: interne component (niet direct gebruikersgericht)

> Meet altijd de duur van startup-fases. Dit kost 1 regel per fase (`time.perf_counter()`) maar bespaart uren aan debugging van trage startups.
