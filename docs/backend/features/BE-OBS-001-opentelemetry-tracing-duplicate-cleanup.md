# BE-OBS-001: Dode OpenTelemetry-bootstrap-duplicaat opgeruimd (scope-correctie)

**Sprint:** AUDIT-ARCH-2026-07-02 Dag 2 Groep 6
**Datum:** 2026-07-02
**Status:** APPROVED
**ADR:** ADR-014

## Probleem (audit-claim, achteraf gecorrigeerd)

De audit claimde "OpenTelemetry tracing nooit aangeroepen/geactiveerd" (SRE-001,
3 bevindingen, oorspronkelijk CRITICAL/HIGH). Pre-fix verificatie toonde aan dat
deze claim onjuist was: `src.core.monitoring.tracing.initialize_tracing()` wordt
al aangeroepen in `create_app()` (`src/core/app_factory.py:359`), gebruikt
`config.otel_enabled` (default=True), en is al gedekt door
`tests/unit/test_opentelemetry.py` (bestond al, groen). Het enige reele probleem:
een tweede, dode, nooit-aangeroepen OTel-bootstrap-implementatie
(`src.core.observability.tracing.setup_tracing()`) die dezelfde
verantwoordelijkheid dupliceerde en een ongebruikte env var `ENABLE_TRACING` las.

## Oplossing

- `setup_tracing()` verwijderd uit `src/core/observability/tracing.py`, samen met
  de imports/type-aliases die uitsluitend daarvoor bestonden (`os`, `Protocol`,
  het volledige `TYPE_CHECKING`-blok, de `*Type`-aliases,
  `HAS_SQLALCHEMY_INSTRUMENTATION`-blok).
- De actief gebruikte utilities in hetzelfde bestand (`get_tracer`,
  `TraceManager`, `traced`, `trace_agent_execution`, etc. -- gebruikt door o.a.
  `copilot/council/members/*.py`, `llm_service.py`) blijven ongewijzigd.
- Module-docstring herschreven om de echte bootstrap-eigenaar
  (`monitoring/tracing.py::initialize_tracing`) expliciet te benoemen.

## Trainingssamenvatting

- Actor: Applicatie-opstart (`create_app` in `src/core/app_factory.py`) en OpenTelemetry-infrastructuur.
- Voorwaarde: `config.otel_enabled` staat op `True` (default); de `opentelemetry` packages zijn beschikbaar.
- Actie (request): Roep `initialize_tracing(app)` aan tijdens FastAPI app-creatie.
- Systeemverwerking: De functie bouwt een `TracerProvider` met service-resource, instantieert een `OTLPSpanExporter` naar `config.otel_exporter_otlp_endpoint`, voegt een `BatchSpanProcessor` toe en instrumenteert de FastAPI app via `FastAPIInstrumentor.instrument_app(app)`. `src/core/observability/tracing.py` levert alleen nog span-helpers (`traced`, `TraceManager`, `trace_db_query`); de dode `setup_tracing()` bootstrap is verwijderd.
- Succesrespons: Console-uitvoer `INFO: OpenTelemetry tracing initialized for service ... sending to ...`; traces worden naar de collector verstuurd.
- Foutrespons: Console-uitvoer `WARNING: OpenTelemetry tracing initialization skipped: ...` bij ontbrekende packages; de app start verder op zonder tracing.
- Uitzonderingen: De nooit-aangeroepen `setup_tracing()` duplicaat bestaat niet meer; er is nu exact een bootstrap-locatie.

## Test bewijs

```
pytest tests/architecture/test_tracing_single_implementation.py \
  tests/unit/observability/test_tracing_spans.py \
  tests/unit/test_opentelemetry.py tests/unit/test_distributed_tracing.py \
  tests/unit/test_startup_tracing_logs.py \
  tests/integration/test_milestone1_foundation.py -v
35 passed

ruff check src/core/observability/tracing.py -- 0 errors
python -m pyright -- 0 errors (baseline)
```

## Reviewers

code-reviewer: CHANGES_REQUESTED -> opgelost -- vereiste dat de TYPE_CHECKING-
imports en `*Type`-aliases ook verwijderd werden (niet alleen de functie zelf),
anders blijft er dode residu-code achter.
performance-reviewer (quality-rol): CHANGES_REQUESTED -> opgelost -- empirisch
`ruff check` gedraaid en exact aangetoond welke 4 extra regels (`import os`,
`Protocol`, `Status, StatusCode` runtime-import, `SQLAlchemyInstrumentor`-blok)
mee moesten om F401 te voorkomen.

## Backlog

Geen. De oorspronkelijke SRE-001 CRITICAL/HIGH-classificatie is een
REJECTED-signaal op de audit -- gemeld aan Rakesh in de final-approver brief in
plaats van stilzwijgend de (onjuiste) oorspronkelijke scope te bouwen.
