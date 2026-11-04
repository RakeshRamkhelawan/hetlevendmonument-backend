# BE-SVC-015 -- ProactiveScheduler app.state Dependencies (WE-020/021)

**ID:** BE-SVC-015
**Datum:** 2026-06-01
**ADR:** ADR-027

## Samenvatting

ProactiveScheduler sloeg altijd alle monitors over (WE-020): `app.state.copilot_service`,
`notification_dispatcher`, `tenant_repo` en `redis_client` werden nooit toegewezen bij
startup. WE-021: `_init_proactive_deps()` ontbrak in de lifespan startup-keten.

## Wijzigingen

| Bestand | Wijziging |
| --- | --- |
| `src/core/copilot/proactive/deps.py` | Nieuw: `_DBTenantRepo` + `_ProactiveServiceProxy` |
| `src/core/app_lifespan.py` | `_init_proactive_deps(app)` + aanroep voor `_init_proactive_scheduler` |

## Architectuurbeslissingen

- **Session-factory pattern**: `_DBTenantRepo` en `_ProactiveServiceProxy` maken een fresh DB-sessie per aanroep. De scheduler is lang-levend; long-lived sessions lekken.
- **`_RefreshingPrefsRepo`**: duck-typed wrapper die fresh `UserNotificationPreferencesRepo` maakt per dispatch-aanroep.
- **Graceful degradation**: `_init_proactive_deps` vangt alle exceptions (non-fatal) — als Redis of DB niet beschikbaar is, blijft app starten en logt warning.

## Trainingssamenvatting

### Flow 1: ProactiveScheduler start succesvol

- **Actor:** `app_lifespan.py` startup
- **Voorwaarde:** Redis en DB beschikbaar bij app startup
- **Actie:** `_init_proactive_deps(app)` loopt door; `_init_proactive_scheduler(app)` vindt `app.state.copilot_service` en `dispatcher` aanwezig
- **Systeemreactie:** Monitors worden geladen; APScheduler jobs geregistreerd
- **Succesrespons:** Log: "[OK] ProactiveScheduler dependencies initialized"; monitors actief
- **Foutrespons:** `_init_proactive_deps` gooit exception → warning gelogd → scheduler slaat over (was al het geval)
- **Uitzonderingen:** Individuele monitors kunnen nog steeds falen (per-monitor try/except in scheduler)
