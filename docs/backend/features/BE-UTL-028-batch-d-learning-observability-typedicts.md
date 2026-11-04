---
id: BE-UTL-028
name: Batch D -- Learning/Observability TypedDicts + Any Hardening
sprint: SP-ANY-D
date: 2026-05-31
status: APPROVED WITH MINOR GAPS
commit: 45bb1f7a
---

# BE-UTL-028 -- Batch D Learning/Observability TypedDicts

## Samenvatting

TypedDicts en concrete typen voor 12 bestanden in learning, observability,
monitoring en workflow. Gate 2 doorlopen in 3 review-rondes.

## Nieuwe TypedDicts

| TypedDict | Bestand | Shape |
|-----------|---------|-------|
| `FeedbackPayload` | learning/worker.py | conversation_id/tenant_id/rating/comment/confidence/context |
| `InsightCleanupDict` | learning/worker.py | tenant_id/days/archived/deleted |
| `ObservationCleanupDict` | learning/worker.py | status/observations |
| `CostLogCleanupDict` | learning/worker.py | status/suggestion_logs |
| `DailyReportDict` | learning/analytics.py | period/date/summary/performance/top_categories |
| `WeeklyReportDict` | learning/analytics.py | period/date_range/summary/roi/performance |
| `ExecutionResultDict` | workflow/worker.py | execution_id/status/result/error/duration_seconds |
| `TaskResultDict` | workflow/worker.py | execution_id/task_ref/status/result/error |
| `HealthStatusDict` | workflow/worker.py | status/workers/queue_depth/uptime_seconds/broker |
| `HealthCheckResultDict` | monitoring/vibe_monitoring.py | status/timestamp/checks |

## Type fixes

| Bestand | Wijziging |
|---------|-----------|
| analytics.py | `db_session: Any \| None` → `AsyncSession \| None` (x3) |
| experiment_tracker.py | `mlflow.pytorch.*` → `# type: ignore[attr-defined]`; `training_parameters` blijft `dict[str,Any]` (numpy scalars) |
| learning/worker.py | Dramatiq enqueue_* return: `Message[dict]` → `Message[Any]` (stubs gap) |
| alert_manager.py | TODO comments verplaatst naar correcte regel |
| observability/metrics.py | TODO comments verplaatst naar correcte regel |
| gdpr_service.py | `type[Any]` + `InstrumentedAttribute` voor SQLAlchemy model/column params |

## Gate 2 beslissingen (3 review-rondes)

- **`FeedbackPayload.tenant_id: str`** niet `int` — Dramatiq-bus serialiseert als JSON string (niet JWT int)
- **Actor parameters blijven `dict[str,Any]`** — Dramatiq deserialiseert JSON naar plain dict; TypedDict dient als caller-documentatie
- **`training_parameters: dict[str, Any]`** — numpy scalars (`np.float64`, `np.int64`) zijn geen Python `int|float` subtypes in mypy
- **`total=False` op alle nieuwe TypedDicts** — voorkomt mypy-fouten bij callers die bare dicts doorgeven
- **3 aparte Cleanup TypedDicts** (niet 1 CleanupStatsDict) — de 3 actors hebben distincte return shapes

## Trainingssamenvatting

### Flow: TypedDict voor Dramatiq actor RETURN (niet parameter)

| Stap | Detail |
|------|--------|
| **Actor** | Type-fix agent |
| **Voorwaarde** | `@dramatiq.actor async def foo(...) -> dict[str, Any]` waarbij WIJ de return dict bouwen |
| **Actie** | Definieer TypedDict; verander return-annotatie; gebruik `TypedDict(key=val)` constructor i.p.v. `{"key": val, **spread}` voor Pyright-compatibiliteit |
| **Systeemverwerking** | Pyright valideert dat return-dict alle verplichte keys bevat |
| **Succesrespons** | TDD-test PASS; ruff clean; geen nieuwe Pyright-errors |
| **Foutrespons** | `reportReturnType: dict[str, str\|int] not assignable to TypedDict` → gebruik `TypedDict(...)` constructor of cast |
| **Uitzondering** | Actor PARAMETER: altijd `dict[str, Any]` — Dramatiq deserialiseert Redis JSON naar plain dict; TypedDict-param veroorzaakt `reportArgumentType` bij callers |

### Flow: TODO-comment op correcte regel plaatsen

| Stap | Detail |
|------|--------|
| **Voorwaarde** | `Any` staat op regel N maar `# TODO` staat op regel N+1 (formatter splitste multi-line) |
| **Actie** | Consolideer naar single-line `param: dict[str, Any]  # TODO(TYPE): Any -- beschrijving` |
| **Succesrespons** | `check_any_gate.py` telt violation als "with TODO" |
| **Uitzondering** | Als single-line te lang wordt (>100 chars): voeg TODO toe als comment op VORIGE regel |

## TDD

- `tests/unit/test_batch_d_type_hardening.py`: 15 tests, 15/15 PASS

## Kwaliteitsresultaten

- `ruff check` 12 bestanden: 0 errors
- Gate 2: 3 review-rondes, APPROVED na correcties
- Scan: 372 → 328 violations (−44, −11.8%)
- Cumulatief: 507 → 328 (−179, −35.3%)
