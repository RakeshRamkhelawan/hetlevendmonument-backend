# BE-DSM-006: SP-DSM-002 Dag 2 -- api/learning.py Strangler Fig naar v1/learning/

**Sprint:** SP-DSM-002 Dag 2
**Datum:** 2026-06-16
**Status:** APPROVED WITH MINOR GAPS

---

## Samenvatting

Migratie van het legacy flat-file `src/core/api/learning.py` (127 violations, HAS_DB
anti-pattern, 4 ADR-003 schendingen, 9 f-string loggers) naar een ADR-033-compliant
3-laags pakketstructuur onder `src/core/api/v1/learning/`.

---

## Gewijzigde bestanden

### Nieuw aangemaakt

| Bestand | Doel |
|---------|------|
| `src/core/api/v1/learning/__init__.py` | Package-initialisatie |
| `src/core/api/v1/learning/dependencies.py` | Facade: forbidden module imports (ADR-033 Laag 2) |
| `src/core/api/v1/learning/router.py` | Aggregator: include rules + analytics sub-routers (16 regels) |
| `src/core/api/v1/learning/rules_router.py` | Feedback + rules CRUD endpoints (159 regels) |
| `src/core/api/v1/learning/analytics_router.py` | Insights, metrics, ROI, reports, ML, regional (165 regels) |

### Bijgewerkt

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/registries/optional.py` | Import-pad: `api.learning` -> `api.v1.learning.router` |
| `.importlinter` | +5 `ignore_imports` voor `learning.dependencies -> forbidden_module` edges |
| `tests/architecture/test_dsm002_groep_c_deferred.py` | xfail -> echte passing test voor `test_api_learning_py_violations_zero` |
| `tests/architecture/test_dsm_api_violations.py` | Ceiling 127 -> 117 |

### Verwijderd

| Bestand | Reden |
|---------|-------|
| `src/core/api/learning.py` | Legacy flat-file volledig gemigreerd naar v1/learning/ |

---

## ADR-033 compliance

| Check | Resultaat |
|-------|-----------|
| router.py max 200 regels | PASS (16 regels) |
| rules_router.py max 200 regels | PASS (159 regels) |
| analytics_router.py max 200 regels | PASS (165 regels) |
| Geen directe forbidden imports in router bestanden | PASS (via dependencies facade) |
| dependencies.py als Facade aggregation layer | PASS (5 entries + .importlinter) |
| Violation scanner: 127 -> 117 (-10) | PASS |

---

## ADR-003 fix (tenant_id)

De legacy `api/learning.py` gebruikte `tenant_id="default"` in 3 endpoints:
- `GET /rules` (list_rules)
- `POST /rules` (create_rule)
- `DELETE /rules/{rule_id}` (delete_rule)

Nieuwe code gebruikt `require_tenant_id()` (gooit automatisch HTTP 401 als geen tenant
in context). Omdat `AdaptationRuleService` methoden `tenant_id: str` verwachten en
`require_tenant_id()` een `int` retourneert, wordt `str(require_tenant_id())` gebruikt.

---

## Logger fixes

9 f-string logger calls omgezet naar `%s: %s` + `exc_info=True` patroon conform
backend-patterns.md #10.

---

## Violations

| Voor | Na | Delta |
|------|----|-------|
| 127 | 117 | -10 |

---

## Testresultaten

| Suite | Resultaat |
|-------|-----------|
| `python -m pyright` | 0 errors, 55 warnings (baseline ongewijzigd) |
| `ruff check src/core/api/v1/learning/` | All checks passed |
| Architecture tests | 150 passed, 19 xfailed (geen regressions) |
| `test_api_learning_py_violations_zero` | PASSED (was XFAIL) |
| Gerichte unit tests (learning + agentic) | 180 passed, 13 skipped (baseline ongewijzigd) |

---

## Openstaande items (pre-existing, buiten scope)

| Issue | Actie |
|-------|-------|
| FA note #1: briefclaim 17 ignore_imports (feitelijk 19) | Documentatie-only, geen code-fix |
| FA note #2: OversightGate dode re-export | BLOCKED: `agentic/websocket.py` importeert OversightGate. Niet verwijderd per brief-instructie. Escaleer naar Rakesh. |
| FA note #3: `gatekeeper/dependencies.py` -> `als.enterprise.gatekeeper_repository` | Backlog toekomstige sprint via ALS service interface |
| Auth uitgecommentarieerd op alle learning endpoints | Pre-existing (was al zo in legacy file). Backlog SP-SEC-xxx |
| `created_at` in RuleResponse is placeholder `datetime.now(timezone.utc)` | Pre-existing. ORM-veld niet gemapped in `AdaptationRuleService`. |


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker
- Voorwaarde: SP-DSM-002 Dag 2: api/learning.py Strangler Fig -> v1/learning/ (127->117 violations, ADR-003 fix, HAS_DB removal) is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker start of gebruikt SP-DSM-002 Dag 2: api/learning.py Strangler Fig -> v1/learning/ (127->117 violations, ADR-003 fix, HAS_DB removal).
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
