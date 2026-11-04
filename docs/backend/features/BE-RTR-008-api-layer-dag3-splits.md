# BE-RTR-008 — API Layer Dag 3 Sub-Router Splits (ADR-033)

**Sprint:** SP-API-002 Dag 3
**Datum:** 2026-06-03
**Status:** DONE

---

## Beschrijving

Drie oversized routers zijn gesplitst in Laag 1 sub-routers van maximaal 200 regels elk,
conform het ADR-033 drie-laags compositie patroon. De Laag 3 registries zijn niet gewijzigd.

### Gesplitste routers

#### compliance/router.py (was 1428r → nu 33r composite)

| Sub-router | Routes | Regels |
|---|---|---|
| `score_router.py` | GET /score, GET /score/history | ~175r |
| `gdpr_summary_router.py` | GET /report/gdpr/summary | ~105r |
| `gdpr_dsar_router.py` | GET /report/gdpr/dsar | ~160r |
| `ai_act_summary_router.py` | GET /report/ai-act/summary | ~105r |
| `ai_act_decisions_router.py` | GET /report/ai-act/decisions | ~185r |
| `integrity_verify_router.py` | GET /integrity/verify, POST /integrity/verify-entry | ~209r `# orphan:exempt` |
| `integrity_status_router.py` | GET /integrity/status | ~98r |
| `pdf_router.py` | GET /report/pdf | `# orphan:exempt` |
| `dependencies.py` | Re-exports get_db, governance services, rate limiters | — |

#### focus_builder/router.py (was 1082r → nu 35r composite)

| Sub-router | Routes | Regels |
|---|---|---|
| `shared.py` | Helpers: enrich_span, get_focus_builder_service, WSUser, etc. | ~132r |
| `flows_router.py` | POST/GET/GET/{id}/PUT/{id}/DELETE/{id} /flows | `# orphan:exempt` |
| `execution_router.py` | POST /flows/{id}/execute, GET /flows/{id}/runs/latest, GET /runs/{run_id} | ~160r |
| `pieces_router.py` | GET /pieces, GET /pieces/{name}/schema, POST /pieces/sync | ~90r |
| `ai_router.py` | POST /ai/suggest, POST /ai/generate | ~120r |
| `ws_status_router.py` | WS /flows/{flow_id}/status | ~91r |
| `ws_chat_router.py` | WS /ws/chat | `# orphan:exempt` |

#### users/router.py (was 469r → nu 18r composite)

| Sub-router | Routes | Regels |
|---|---|---|
| `shared.py` | Helpers: has_role, can_manage_users, _get_tenant_scoped_roles | ~55r |
| `me_router.py` | GET /me, PUT /me, PUT /{user_id}/password | ~126r |
| `users_list_router.py` | POST /, GET / | ~148r |
| `users_detail_router.py` | GET /{user_id}, PUT /{user_id}, DELETE /{user_id} | ~177r |
| `dependencies.py` | Re-exports get_db, get_current_user, AuthService, jwt_handler | — |

---

## Bestanden

- `src/core/api/v1/compliance/score_router.py`
- `src/core/api/v1/compliance/gdpr_summary_router.py`
- `src/core/api/v1/compliance/gdpr_dsar_router.py`
- `src/core/api/v1/compliance/ai_act_summary_router.py`
- `src/core/api/v1/compliance/ai_act_decisions_router.py`
- `src/core/api/v1/compliance/integrity_verify_router.py`
- `src/core/api/v1/compliance/integrity_status_router.py`
- `src/core/api/v1/compliance/pdf_router.py`
- `src/core/api/v1/compliance/dependencies.py`
- `src/core/api/v1/compliance/router.py` (composite, updated)
- `src/core/api/v1/focus_builder/shared.py`
- `src/core/api/v1/focus_builder/flows_router.py`
- `src/core/api/v1/focus_builder/execution_router.py`
- `src/core/api/v1/focus_builder/pieces_router.py`
- `src/core/api/v1/focus_builder/ai_router.py`
- `src/core/api/v1/focus_builder/ws_status_router.py`
- `src/core/api/v1/focus_builder/ws_chat_router.py`
- `src/core/api/v1/focus_builder/router.py` (composite, updated)
- `src/core/api/v1/users/shared.py`
- `src/core/api/v1/users/me_router.py`
- `src/core/api/v1/users/users_list_router.py`
- `src/core/api/v1/users/users_detail_router.py`
- `src/core/api/v1/users/dependencies.py`
- `src/core/api/v1/users/router.py` (composite, updated)

---

## Kritieke invarianten

- **URL-freeze (ADR-031):** Geen enkele compliance URL gewijzigd.
- **agents_router behouden:** `focus_builder/router.py` include_router voor agents_router met `prefix=""`.
- **Geen `from __future__ import annotations`** in nieuwe bestanden.
- **Laag 3 registries niet gewijzigd.**

---

## Tests

- 100/100 unit/api tests PASS
- 15/15 architecture equivalentietests PASS (inclusief 3 nieuwe Dag 3 tests)

---

## Trainingssamenvatting

### Flow 1: Compliance Score ophalen

| Stap | Details |
|---|---|
| **Actor** | Geverifieerde gebruiker (tenant admin of regular user) |
| **Voorwaarde** | Geldig JWT token; score_router.py beschikbaar |
| **Actie** | GET /api/v1/compliance/score |
| **Systeemverwerking** | JWT -> tenant_id -> ComplianceScoreCalculator.calculate_overall_score() |
| **Succesrespons** | HTTP 200 + ComplianceScoreResponse (overall, gdpr, ai_act, audit scores) |
| **Foutrespons** | HTTP 401 (geen auth), HTTP 500 (berekeningsfout) |
| **Uitzonderingen** | governance_read_limit rate limiter (429 bij overschrijding) |

### Flow 2: FocusBuilder flow aanmaken

| Stap | Details |
|---|---|
| **Actor** | Gebruiker met WRITE permission |
| **Voorwaarde** | Geldig JWT; flows_router.py beschikbaar |
| **Actie** | POST /api/v1/focus-builder/flows met FlowCreate body |
| **Systeemverwerking** | Auth -> permission check -> FocusBuilderService.create_flow() -> twin tracking |
| **Succesrespons** | HTTP 201 + FlowRead |
| **Foutrespons** | HTTP 400 (validatie), HTTP 500 (intern) |
| **Uitzonderingen** | GraphValidationError -> HTTP 400; limiter 10/minute |

### Flow 3: User profiel ophalen

| Stap | Details |
|---|---|
| **Actor** | Geverifieerde gebruiker |
| **Voorwaarde** | Geldig JWT token; me_router.py beschikbaar |
| **Actie** | GET /api/v1/users/me |
| **Systeemverwerking** | JWT -> get_current_user -> UserResponse.model_validate() |
| **Succesrespons** | HTTP 200 + UserResponse |
| **Foutrespons** | HTTP 401 (niet geauthenticeerd) |
| **Uitzonderingen** | Geen rate limiter op /me |
