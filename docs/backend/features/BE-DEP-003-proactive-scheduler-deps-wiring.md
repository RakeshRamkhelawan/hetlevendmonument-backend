# BE-DEP-003 -- ProactiveScheduler 7 app.state Dependencies Wiring

**Sprint:** SP-WE-21
**Bron:** NEW-WIRE-004
**ADR:** ADR-027
**Datum:** 2026-06-01
**Status:** APPROVED WITH MINOR GAPS

---

## Overzicht

`src/core/app_lifespan.py::_init_proactive_deps()` wired alleen 4 van de 13
`app.state`-attributen die `_init_proactive_scheduler()` leest. De 9 ontbrekende
attributen waren altijd `None`, waardoor 5 van de 10 proactive monitors stil
werden overgeslagen (interval-based scheduler startte zelfs niet als geen enkele
monitor instantieerbaar was).

Deze feature voegt `_wire_proactive_extras(app, session_factory)` toe -- een
helper die de overgebleven dependencies in `app.state` zet:

| `app.state.*`        | Source                                  | Doel monitor                        |
|----------------------|-----------------------------------------|-------------------------------------|
| `health_registry`    | `InMemoryHealthMonitorRegistry`         | AgentHealthMonitor                  |
| `failover_provider`  | `get_fallback_chain()` (module-singleton) | CircuitBreakerMonitor             |
| `prometheus_client`  | `StubPrometheusClient`                  | WorkflowLatency + TokenSpike        |
| `consent_repo`       | `StubConsentRepo(session_factory)`      | ConsentExpiryMonitor                |
| `audit_repo`         | `StubAuditRepo(session_factory)`        | AuditAnomalyMonitor                 |
| `role_repo`          | `StubRoleRepo(session_factory)`         | AuditAnomalyMonitor (grace period)  |
| `workflow_repo`      | `StubWorkflowRepo(session_factory)`     | SensitiveWorkflowMonitor            |
| `pii_scanner`        | `StubWorkflowPIIScanner`                | SensitiveWorkflowMonitor            |
| `dpia_repo`          | `StubDPIARepo(session_factory)`         | SensitiveWorkflowMonitor            |

De stubs leven in `src/core/copilot/proactive/stub_repos.py` en retourneren
unconditioneel lege resultaten -- monitors bouwen wel correct op maar emit geen
signalen tot productie-implementaties beschikbaar zijn. Dit is bewust technische
schuld: het wirinen mag de scheduler niet blokkeren.

## Bestanden

- `src/core/app_lifespan.py` -- `_init_proactive_deps()` roept aan het einde
  `_wire_proactive_extras()` aan; logger.info vermeldt nu alle 13 keys.
- `src/core/copilot/proactive/stub_repos.py` -- nieuwe module met 7 stub klassen.
- `tests/unit/test_sp_we_21_proactive_scheduler_deps.py` -- 19 unit tests.

## Trainingssamenvatting

### Flow: ProactiveScheduler startup met volledige dependencies

- **Actor:** `app_lifespan` startup routine (`lifespan_manager`).
- **Voorwaarde:** Database geinitialiseerd, Redis bereikbaar, SP-WE-18 logica
  beschikbaar in `src.core.als.registry` (`InMemoryHealthMonitorRegistry`).
- **Actie:** Lifespan roept achtereenvolgens aan:
  1. `_init_proactive_deps(app)` -- wired core + extras (via
     `_wire_proactive_extras(app, get_async_session)`).
  2. `_init_compliance_monitors(app)` -- event-driven monitors.
  3. `_init_proactive_scheduler(app)` -- bouwt APScheduler-instantie.
- **Systeemverwerking:**
  - `_wire_proactive_extras()` set alle 9 ontbrekende `app.state`-attributen.
  - Elk blok is geguard: bestaat het attribuut al (door eerdere subsystem zoals
    SP-WE-18), dan wordt het niet overschreven.
  - Per-attribute try/except blokken zorgen voor graceful degradation: een
    importfout in een specifieke stub stopt niet de overige wirings.
  - `_init_proactive_scheduler()` leest alle 13 keys; alle monitors waarvoor
    deps aanwezig zijn worden geinstantieerd; APScheduler start.
  - `app.state.proactive_scheduler` wordt gezet.
- **Succesrespons:** Logger toont
  `"[OK] ProactiveScheduler started with N interval-based monitors"` met N >= 5.
- **Foutrespons:** Faalt een specifieke dep (`ImportError`, `ValueError`,
  `RuntimeError`), dan logt `_wire_proactive_extras()` een waarschuwing en de
  bijbehorende monitor wordt door `_init_proactive_scheduler()` overgeslagen.
  De applicatie blijft starten.
- **Uitzonderingen:** Als `copilot_service` of `notification_dispatcher` na
  `_init_proactive_deps()` nog steeds `None` is (Redis onbereikbaar), keert
  `_init_proactive_scheduler()` vroeg terug -- bestaand gedrag, geen wijziging.

## Beveiliging en GDPR

- Stubs retourneren geen tenant-data; geen cross-tenant lek mogelijk.
- `StubRoleRepo.was_any_role_created_after` retourneert `False` (geen grace
  period) -- fail-safe: anomalies worden niet onterecht onderdrukt.
- `StubDPIARepo.exists_for_workflow` retourneert `False`; gecombineerd met
  `StubWorkflowRepo.list_active() == []` betekent dit nul signalen.
- Geen secrets, geen URLs, ASCII-only.

## Technische schuld

- Productie-implementaties van `ConsentRepository`, `AuditRepository`,
  `RoleRepository`, `WorkflowRepository`, `DPIARepository`, `WorkflowPIIScanner`,
  en een echte `PrometheusClient` zijn nog niet gewired. Stubs blokkeren niets
  maar leveren ook geen waarde tot ze vervangen worden.

## Tests

- 19 unit tests in `tests/unit/test_sp_we_21_proactive_scheduler_deps.py`:
  - 11 wiring tests (alle 9 keys + idempotency + import check)
  - 7 stub Protocol-compliance tests
  - 1 startup-volgorde verifiatie (statisch: deps voor scheduler)

## Acceptatiecriteria

- [x] `_wire_proactive_extras()` aanwezig en aangeroepen door `_init_proactive_deps()`.
- [x] Alle 9 `app.state`-attributen worden gezet (of guarded gelaten bij failure).
- [x] Bestaande waarden worden niet overschreven (idempotency).
- [x] Ruff + mypy clean op gewijzigde bestanden.
- [x] 19/19 tests GROEN; geen regressies in `tests/unit`.

---

*Sprint SP-WE-21 | Status: CLOSED | 2026-06-01*
