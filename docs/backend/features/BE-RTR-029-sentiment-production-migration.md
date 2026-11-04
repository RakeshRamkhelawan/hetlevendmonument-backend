# BE-RTR-029 — Sentiment Scanner + Production Domain Migration naar v1/

**Sprint:** SP-API-006 Dag 4
**Datum:** 2026-06-05
**Commit:** 92aad2fc
**Status:** IMPLEMENTED

---

## Samenvatting

Twee flat-file routers gemigreerd naar ADR-033 drie-laags structuur:

| Bronbestand | Doelmap | Routes |
|-------------|---------|--------|
| `src/core/api/sentiment_scanner_endpoints.py` (451r) | `v1/sentiment_scanner/` | 5 routes |
| `src/core/api/production_endpoints.py` (573r) | `v1/production/` | 9 routes |

---

## Architectuur

### v1/sentiment_scanner/

```
v1/sentiment_scanner/
|- __init__.py        (domain_router prefix="/api/v1/agents")
|- router.py          (composite)
|- scanner_router.py  (alle 5 routes, prefix="/api/v1/sentiment-scanner")
|- dependencies.py
```

**Dubbele prefix bewaard:** De legacy registratie in `agents.py` voegde
`prefix="/api/v1/agents"` toe en de sub-router heeft `prefix="/api/v1/sentiment-scanner"`.
Gecombineerd: `/api/v1/agents/api/v1/sentiment-scanner/...`. Dit gedrag is pre-existing
en expliciet gerepliceerd in `__init__.py` (`domain_router = APIRouter(prefix="/api/v1/agents")`).

### v1/production/

```
v1/production/
|- __init__.py           (domain_router prefix="/api")
|- router.py             (composite, prefix="/v1/production")
|- health_router.py      (GET /health, GET /health-assessment, GET /deployment-status)
|- operations_router.py  (POST /initialize, POST /test/comprehensive, GET /system-integration-status, POST /restart-system)
|- reporting_router.py   (GET /production-report, GET /performance-baseline)
|- shared.py             (ProductionIntegrationManager singleton)
|- dependencies.py
```

Gecombineerde routes landen op `/api/v1/production/...` (analytics.py voegt `/api` toe,
router.py heeft prefix `/v1/production`).

---

## Wijzigingen registries

| Bestand | Voor | Na |
|---------|------|-----|
| `registries/agents.py` | `from src.core.api.sentiment_scanner_endpoints import router` + `prefix="/api/v1/agents"` | lazy `from src.core.api.v1.sentiment_scanner import domain_router` |
| `registries/analytics.py` | `from src.core.api.production_endpoints import router` + `prefix="/api"` | lazy `from src.core.api.v1.production import domain_router` |

---

## Routes

### Sentiment Scanner (`/api/v1/agents/api/v1/sentiment-scanner/`)

| Method | Path | Scope |
|--------|------|-------|
| GET | /status | AGENTS_READ |
| POST | /analyze | AGENTS_WRITE |
| POST | /batch-analyze | AGENTS_WRITE |
| POST | /generate-report | AGENTS_READ |
| GET | /demo | AGENTS_READ |

### Production (`/api/v1/production/`)

| Method | Path | Scope |
|--------|------|-------|
| GET | /health | AGENTS_READ |
| GET | /health-assessment | ADMIN_ALL |
| GET | /deployment-status | AGENTS_READ |
| POST | /initialize | ADMIN_ALL |
| POST | /test/comprehensive | ADMIN_ALL |
| GET | /system-integration-status | AGENTS_READ |
| POST | /restart-system | ADMIN_ALL |
| GET | /production-report | AGENTS_READ |
| GET | /performance-baseline | AGENTS_READ |

---

## Pre-existing issues

| Issue | Actie |
|-------|-------|
| f-strings in logger calls in original sentiment_scanner_endpoints.py | Gefixed in v1/scanner_router.py (gebruik `%s` formatting) |
| f-strings in logger calls in original production_endpoints.py | Gefixed in alle v1/production/ sub-routers |
| `sys.path.append` in sentinel_scanner_endpoints.py | Niet overgenomen in v1/ (was onnodige path manipulation) |

---

## Tests

- `test_sentiment_scanner_flat_file_migrated_to_v1` — GROEN
- `test_production_flat_file_migrated_to_v1` — GROEN
- Totaal: 154/154 PASS, 0 regressions op 152 bestaande tests

---

## Trainingssamenvatting

### Flow 1: GET /api/v1/agents/api/v1/sentiment-scanner/status

| Aspect | Detail |
|--------|--------|
| **Actor** | Geauthenticeerde gebruiker met AGENTS_READ scope |
| **Voorwaarde** | Geldig JWT token, AGENTS_READ scope aanwezig |
| **Actie** | GET /api/v1/agents/api/v1/sentiment-scanner/status |
| **Systeemverwerking** | scanner_router.get_scanner_status() retourneert naam, versie, capabilities |
| **Succesrespons** | HTTP 200 met scanner info JSON |
| **Foutrespons** | HTTP 401 (geen auth), HTTP 403 (geen scope) |
| **Uitzonderingen** | HTTP 500 bij interne fout (exc_info=True gelogd) |

### Flow 2: POST /api/v1/production/initialize

| Aspect | Detail |
|--------|--------|
| **Actor** | Admin gebruiker met ADMIN_ALL scope |
| **Voorwaarde** | Geldig JWT, ADMIN_ALL scope |
| **Actie** | POST /api/v1/production/initialize met InitializationRequest body |
| **Systeemverwerking** | operations_router.initialize_production_systems() roept ProductionIntegrationManager.initialize_all_systems() aan |
| **Succesrespons** | HTTP 200 met InitializationResponse (total_systems, success_rate, overall_status) |
| **Foutrespons** | HTTP 401/403 (auth), HTTP 500 bij manager failure |
| **Uitzonderingen** | Stub retourneert altijd 7/7 systemen (Phase 0) |
