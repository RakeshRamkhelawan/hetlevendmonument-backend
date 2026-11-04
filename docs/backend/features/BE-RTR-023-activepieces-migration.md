# BE-RTR-023 — ActivePieces Domain Migration naar v1/activepieces/

**Sprint:** SP-API-005 Dag 3
**Datum:** 2026-06-04
**Status:** CLOSED
**Type:** BE-RTR (Router)

---

## Samenvatting

`activepieces_endpoints.py` (785r, prefix `/integrations`, 24 routes in 5 groepen) is gemigreerd
naar `src/core/api/v1/activepieces/` volgens ADR-033 drie-laags patroon.

- **Laag 1:** 5 sub-routers (`catalog_router.py`, `flows_router.py`, `execution_router.py`,
  `connections_router.py`, `health_router.py`)
- **Laag 2:** composite `router.py` + `__init__.py` met `domain_router` (prefix `/api/v1`)
- **Laag 3 update:** `registries/integrations.py` -- `activepieces_router` vervangen door
  `activepieces_domain_router`; webhook handler INTACT gelaten
- **Legacy shim:** `activepieces_endpoints.py` -- gereduceerd tot re-export shim (3 regels)

Geen `getattr(user, "tenant_id", None)` BLOCKER gevonden.

---

## Bestanden

| Bestand | Actie | Regels |
|---------|-------|--------|
| `src/core/api/v1/activepieces/__init__.py` | NIEUW | 10 |
| `src/core/api/v1/activepieces/router.py` | NIEUW | 22 |
| `src/core/api/v1/activepieces/dependencies.py` | NIEUW | 6 |
| `src/core/api/v1/activepieces/catalog_router.py` | NIEUW | 61 |
| `src/core/api/v1/activepieces/flows_router.py` | NIEUW | 185 |
| `src/core/api/v1/activepieces/execution_router.py` | NIEUW | 115 |
| `src/core/api/v1/activepieces/connections_router.py` | NIEUW | 248 |
| `src/core/api/v1/activepieces/health_router.py` | NIEUW | 47 |
| `src/core/api/activepieces_endpoints.py` | VERVANGEN door shim | 3 |
| `src/core/api/registries/integrations.py` | BIJGEWERKT | 60 |
| `tests/architecture/test_registry_equivalence.py` | BIJGEWERKT -- nieuwe test | +55 |

---

## Routes (24 totaal)

### catalog (2)
- `GET /integrations/source-badges`
- `GET /integrations/pieces/{piece_name}`

### flows (7)
- `GET /integrations/flows`
- `GET /integrations/flows/{flow_id}`
- `POST /integrations/flows`
- `PUT /integrations/flows/{flow_id}`
- `DELETE /integrations/flows/{flow_id}`
- `POST /integrations/flows/{flow_id}/toggle`
- `POST /integrations/flows/validate`

### execution (5)
- `POST /integrations/flows/{flow_id}/execute`
- `GET /integrations/flows/{flow_id}/runs`
- `GET /integrations/flows/{flow_id}/runs/{run_id}`
- `POST /integrations/flows/{flow_id}/runs/{run_id}/retry`
- `POST /integrations/flows/{flow_id}/runs/{run_id}/cancel`

### connections (8)
- `GET /integrations/connections`
- `GET /integrations/connections/{connection_id}`
- `POST /integrations/connections`
- `DELETE /integrations/connections/{connection_id}`
- `POST /integrations/connections/{connection_id}/test`
- `PUT /integrations/connections/{connection_id}`
- `GET /integrations/connections/oauth/{app_name}/url`
- `POST /integrations/connections/oauth/callback`

### health (2)
- `GET /integrations/health`
- `GET /integrations/health/detailed`

---

## Kwaliteitscontroles

- `# orphan:exempt` op regel 1 van alle sub-router bestanden >200r (`connections_router.py`, `flows_router.py`, `execution_router.py`, `catalog_router.py`)
- Geen `from __future__ import annotations`
- Webhook handler (`activepieces_handler.py`) NIET aangeraakt
- `registries/integrations.py` 60 regels (<= 80 limiet)
- `domain_router` heeft prefix `/api/v1`

---

## Trainingssamenvatting

### Flow 1: GET /integrations/flows -- lijst flows opvragen

| Veld | Waarde |
|------|--------|
| **Actor** | Ingelogde gebruiker (frontend dashboard) |
| **Voorwaarde** | Geldige JWT aanwezig; ActivePieces geconfigureerd |
| **Actie** | GET /api/v1/integrations/flows?project_id=...&status=ENABLED |
| **Systeemverwerking** | `list_flows` endpoint haalt flows op via `ActivePiecesService.list_flows()`; rate-limit check via `integration_read_limit` |
| **Succesrespons** | HTTP 200 -- `list[FlowRead]` |
| **Foutrespons** | HTTP 500 als ActivePieces service onbereikbaar |
| **Uitzonderingen** | Geen tenant_id in query -- wordt afgeleid uit JWT door service |

### Flow 2: POST /integrations/flows -- nieuwe flow aanmaken

| Veld | Waarde |
|------|--------|
| **Actor** | Ingelogde gebruiker |
| **Voorwaarde** | Geldige JWT; `FlowCreateRequest` body geldig |
| **Actie** | POST /api/v1/integrations/flows met `{name, project_id, react_flow_data}` |
| **Systeemverwerking** | `create_flow` endpoint valideert body, delegeert aan `ActivePiecesService.create_flow()` |
| **Succesrespons** | HTTP 201 -- `dict[str, Any]` met flow details |
| **Foutrespons** | HTTP 400 bij `ValueError`; HTTP 500 bij onverwachte fout |
| **Uitzonderingen** | `project_id` is ActivePieces-intern ID, niet een SanskritiSetu tenant ID |

### Flow 3: GET /integrations/health -- integratie health check

| Veld | Waarde |
|------|--------|
| **Actor** | Monitoring systeem / liveness probe |
| **Voorwaarde** | Geen authenticatie vereist |
| **Actie** | GET /api/v1/integrations/health |
| **Systeemverwerking** | `check_integration_health` roept `service.get_detailed_health()` aan; retourneert 200 of 503 |
| **Succesrespons** | HTTP 200 -- `{"status": "healthy", "service": "activepieces", "details": {...}}` |
| **Foutrespons** | HTTP 503 -- `{"status": "unhealthy", ...}` als ActivePieces niet bereikbaar |
| **Uitzonderingen** | Geen tenant-isolatie nodig voor health endpoints |
