"""AUDIT-ARCH-2026-07-02 Groep 6 -- dode tracing-duplicaat opgeruimd (scope-correctie).

De audit claimde "OpenTelemetry nooit aangeroepen/geactiveerd" (SRE-001, 3 bevindingen).
Verificatie tijdens Dag 2 toonde aan dat deze claim FOUT was: er bestonden twee
parallelle OTel-bootstrap-implementaties.

- `src.core.observability.tracing.setup_tracing(app)` -- volledig uitgewerkt
  (OTLP/Jaeger, BatchSpanProcessor), maar nergens aangeroepen. Leest een env var
  `ENABLE_TRACING` die nergens gezet wordt.
- `src.core.monitoring.tracing.initialize_tracing(app)` -- wordt WEL aangeroepen in
  `create_app()` (zie `tests/unit/test_opentelemetry.py::test_tracing_called_in_production_mode`,
  al groen), gebruikt `config.otel_enabled` (default=True).

Tracing was dus al actief -- het enige reele probleem was verwarrende, dode
duplicaat-code (zelfde patroon als de dubbele-AuditService-vondst uit Dag 1, maar
dan voor observability). Deze test faalt zodra `setup_tracing` opnieuw verschijnt,
of zodra de actief gebruikte tracing-utilities uit hetzelfde bestand (get_tracer,
TraceManager, etc. -- gebruikt door o.a. copilot/council/members/*.py) per ongeluk
mee weggehaald worden.
"""

import importlib

import src.core.observability.tracing as observability_tracing


def test_setup_tracing_dead_duplicate_is_removed() -> None:
    """De dode, nooit-aangeroepen OTel-bootstrap-duplicaat mag niet terugkomen."""
    importlib.reload(observability_tracing)
    assert not hasattr(observability_tracing, "setup_tracing"), (
        "setup_tracing() is teruggekomen in src/core/observability/tracing.py -- dit is "
        "een dode duplicaat-bootstrap-functie (nooit aangeroepen, leest de ongebruikte "
        "env var ENABLE_TRACING). De echte, actief-gewired implementatie is "
        "src.core.monitoring.tracing.initialize_tracing(), aangeroepen in create_app()."
    )
    assert "setup_tracing" not in observability_tracing.__all__


def test_actively_used_tracing_utilities_still_present() -> None:
    """Alleen setup_tracing() was dood -- de rest van dit bestand wordt echt gebruikt
    (o.a. src/core/copilot/council/members/*.py, src/core/llm/llm_service.py)."""
    for name in ("get_tracer", "TraceManager", "HAS_OPENTELEMETRY", "traced"):
        assert hasattr(observability_tracing, name), (
            f"{name} ontbreekt in src/core/observability/tracing.py -- dit wordt elders "
            "actief gebruikt en mag niet per ongeluk verwijderd zijn bij het opruimen "
            "van de dode setup_tracing()-duplicaat."
        )
