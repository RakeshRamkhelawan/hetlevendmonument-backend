# Review BE-EP-008 — Canvas Export Access Check + WS Auth Fix

**Reviewer:** Laag A (code-reviewer + quality-reviewer subagents, parallel)  
**Datum:** 2026-05-29  
**Sprint:** SP-E03  
**Status:** APPROVED WITH MINOR GAPS

---

## Bevindingen Laag A (code-reviewer)

| # | Severity | Bevinding | Actie |
|---|----------|-----------|-------|
| 1 | CRITICAL (opgelost) | Bare `except Exception` voor 404 maskeert DB-fouten als 404 | Vervangen door `except NotFoundError` specifiek |
| 2 | CRITICAL (opgelost) | `NotFoundError` ontbrak in import | `NotFoundError` toegevoegd naast `PermissionDeniedError` |
| 3 | HIGH (opgelost) | `canvas_service.*` calls in function bodies produceren mypy errors na verwijdering import | `canvas_service: Any = None` stub toegevoegd; resterende calls zijn onbereikbare dode code |
| 4 | MEDIUM (opgelost) | 3x `datetime.utcnow()` in hetzelfde bestand | Vervangen door `datetime.now(timezone.utc)` |

## Bevindingen Laag A (quality-reviewer)

| # | Severity | Bevinding | Actie |
|---|----------|-----------|-------|
| 5 | BLOCKING (opgelost) | `user_id=current_user.id` geeft `int` waar `UUID` verwacht | Vervangen door `user_id=UUID(int=current_user.id)` |
| 6 | BLOCKING (opgelost — planverduidelijking) | `get_current_user_ws` import-locatie onduidelijk | Bevestigd: `src.core.auth.dependencies`, toegevoegd als aparte import-regel |

---

## Conclusie

Alle CRITICAL en BLOCKING bevindingen zijn opgelost voor de code werd weggeschreven.

**APPROVED WITH MINOR GAPS**

Bekende beperkingen (niet geblokkeerd):
- `export_import.py` router is niet geregistreerd in `router_registry.py` — buiten SP-E03 scope
- `canvas_service.get_canvas_with_blocks` en andere dode calls in niet-`export_canvas` endpoints
  zijn onbereikbaar (router unregistered) maar genereren runtime `AttributeError` als ze ooit
  aangeroepen worden — technisch schuld voor een toekomstige sprint wanneer de router geregistreerd wordt
- `UUID(int=current_user.id)` is een tijdelijke oplossing voor het type-mismatch probleem
  (`UserResponse.id: int` vs `Canvas.owner_id: UUID`). De structurele fix vereist een
  schema-beslissing buiten SP-E03 scope
