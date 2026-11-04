# BE-API-002: SP-API-011 Dag 2 -- Router split governance_admin (ADR-033)

## Metadata

| Veld | Waarde |
|------|--------|
| ID | BE-API-002 |
| Sprint | SP-API-011 Dag 2 |
| Status | APPROVED |
| Datum | 2026-06-19 |
| Auteur | Claude (Sonnet 4.6) |

---

## Samenvatting

ADR-033 legt een harde grens van 200 regels per `router.py`. Dag 2 splitst de governance_admin router:

| Bestand | Voor | Na |
|---------|------|-----|
| `src/core/api/v1/governance_admin/router.py` | 528 regels | 36 regels (composiet) |

---

## Gewijzigde bestanden

### Nieuw aangemaakt

| Bestand | Inhoud |
|---------|--------|
| `src/core/api/v1/governance_admin/schemas.py` | 4 enums + 6 Pydantic modellen (~96r) |
| `src/core/api/v1/governance_admin/dependencies.py` | `get_tenant()` + `get_user_id()` (~26r) |
| `src/core/api/v1/governance_admin/router_anomalies.py` | `calculate_severity`, `generate_sample_anomalies`, `calculate_anomaly_stats`, GET /anomalies (~215r) |
| `src/core/api/v1/governance_admin/router_risk.py` | `calculate_risk_level`, `generate_risk_assessment`, GET /risks/{mission_id} (~166r) |

### Gewijzigd

| Bestand | Wijziging |
|---------|-----------|
| `src/core/api/v1/governance_admin/router.py` | Composiet: 528r -> 36r. Re-exports alle 20 symbolen voor legacy shim. |
| `tests/unit/test_governance_endpoints.py` | 2 patch-targets bijgewerkt: `router.get_current_tenant_id` -> `dependencies.get_current_tenant_id` |
| `tests/architecture/test_dsm_grade_a_plus.py` | xfail reason bijgewerkt: "4 oversized routers" -> "1 oversized router remaining: auth/router.py (Dag 3)" |

### Ongewijzigd

- `src/core/api/governance_endpoints.py` (legacy shim) -- importeert 20 symbolen van composiet; werkt ongewijzigd
- `src/core/api/v1/governance_admin/__init__.py` -- importeert `router` van composiet; werkt ongewijzigd
- `src/core/api/registries/core_api.py` -- geen wijziging nodig

---

## ADR-033 Laag 1 patroon

- Composiet `router.py`: `APIRouter(prefix="/api/v1/governance", tags=["governance"])` + `include_router()` per sub-router + re-exports voor legacy shim
- Sub-routers: `APIRouter(tags=["governance"])` zonder prefix (prefix geerfend van composiet)
- `schemas.py`: puur data (enums + Pydantic modellen, geen APIRouter)
- `dependencies.py`: gedeelde dependency-functies (geen APIRouter)

---

## Legacy shim re-exports (alle 20 symbolen)

Composiet `router.py` re-exporteert via `# noqa: F401`:
- **Enums (4)**: AnomalyType, AnomalySeverity, RiskCategory, RiskLevel (van schemas.py)
- **Modellen (6)**: AnomalyDetail, AnomalyStats, AnomaliesResponse, RiskFactor, RiskAssessment, RiskResponse (van schemas.py)
- **Shared helpers (2)**: get_tenant, get_user_id (van dependencies.py)
- **Anomaly helpers (3)**: calculate_severity, generate_sample_anomalies, calculate_anomaly_stats (van router_anomalies.py)
- **Risk helpers (2)**: calculate_risk_level, generate_risk_assessment (van router_risk.py)
- **Endpoints (2)**: get_anomalies, get_risk_assessment (van sub-routers)
- **Router (1)**: router zelf (composiet APIRouter)

---

## Testresultaten

```
78 passed, 2 xfailed
```

- `tests/unit/test_governance_endpoints.py`: 64/64 PASS (alle helper, model, enum, endpoint tests)
- `tests/architecture/test_api_layer.py::test_no_orphan_routers`: PASS
- `tests/architecture/test_api_layer.py::test_no_router_files_over_200_lines`: PASS
- `tests/architecture/test_dsm_grade_a_plus.py::test_router_size_limit_adr033`: XFAIL (1 oversized router resterend: auth/router.py Dag 3)

---

## Pyright

```
0 errors, 55 warnings
```

Baseline (commit b1398e4c) intact.

---

## Oversized routers na Dag 2

| Bestand | Regels | Dag |
|---------|--------|-----|
| `src/core/api/auth/router.py` | 1107 | Dag 3 |


## Trainingssamenvatting

- Actor: Beheerder
- Voorwaarde: SP-API-011 Dag 2: governance_admin/router.py 528r->36r. schemas.py + dependencies.py + 2 sub-routers aangemaakt. 20 re-exports voor legacy shim. 2 patch-targets bijgewerkt. 78 tests PASS. is beschikbaar en correct geconfigureerd.
- Actie: Beheerder start of gebruikt SP-API-011 Dag 2: governance_admin/router.py 528r->36r. schemas.py + dependencies.py + 2 sub-routers aangemaakt. 20 re-exports voor legacy shim. 2 patch-targets bijgewerkt. 78 tests PASS..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
