# Review: BE-SVC-005 EU AI Act Compliance Services

## Reviewer
Automated code-reviewer + doc-reviewer subagents (Laag A), 2 review iteraties

## Datum
2026-05-29

## Bevindingen

### Iteratie 1 (v1) — APPROVED WITH MINOR GAPS (na code-fix)

| Ernst | Bevinding | Status |
|-------|-----------|--------|
| HIGH | `incident_router.py` niet geregistreerd in `router_registry.py` (alle endpoints 404 in productie) | Opgelost: `_register_ai_act_incidents()` toegevoegd aan `router_registry.py` |
| MEDIUM | `update_status()` zette `resolved_at` niet -- spec beschreef toekomstige intentie als huidige werkelijkheid | Opgelost: `resolved_at = now()` bij RESOLVED, reset naar `None` bij andere statussen |
| MEDIUM | `log_provenance()` signature in spec onjuist: nam 5 losse args, werkelijke signature is `(record: ProvenanceRecord) -> ModelProvenanceDB` | Opgelost in v2 |
| MINOR | `list_incidents` mist `severity` en `agent_id` filter parameters | Gedocumenteerd als minor gap |
| MINOR | `list_provenance` mist `provider` en `model` filter parameters | Gedocumenteerd als minor gap |
| MINOR | Geen acceptatiecriteria sectie | Acceptabel -- verwezen naar BE-MDL-007 |
| MINOR | Router registratie ontbrak in spec | Opgelost in v2 (Router registratie sectie toegevoegd) |

### Code-fixes uitgevoerd

1. **`incident_service.py` - `update_status()`**: `resolved_at = datetime.now(timezone.utc)` toegevoegd
   bij `IncidentStatus.RESOLVED`; reset naar `None` bij andere statussen (voorkomt stale compliance record).
2. **`router_registry.py`**: `_register_ai_act_incidents(app)` functie toegevoegd en aangeroepen
   vanuit `register_all_routers()`. Geen try/except -- EU AI Act compliance routers mogen niet
   stil falen bij startup.

### ADR en security naleving geverifieerd

- `tenant_id` altijd uit `get_current_user()` (JWT) -- nooit uit request body.
- Geen `from __future__ import annotations` in `incident_router.py` (FastAPI valkuil Sprint 4 Dag 2).
- Route `/eu-reporting/pending` voor `/{incident_id}` gedeclareerd (path collision fix).
- `alert_manager.py` gebruikt `flush()` niet `commit()` -- outer transaction intact.
- `compute_hash()` retourneert 64-char SHA-256 hex (geen truncatie).

### Overgebleven minor gaps

1. `list_incidents` heeft ook `severity` en `agent_id` filters (in router) die de spec niet toont.
2. `list_provenance` heeft ook `provider` en `model` filters die de spec niet toont.
3. `from __future__ import annotations` in `incident_service.py` is veilig (FastAPI introspects geen
   service-bestanden), maar spec geeft geen uitleg -- voedt mogelijke cargo-culting.

## Verdict

**APPROVED WITH MINOR GAPS**

Alle HIGH bevindingen opgelost via code-fixes en spec-updates. Minor gaps zijn documentatief
van aard en blokkeren implementatie niet. SP-E04 Dag 2 is klaar voor merge.
