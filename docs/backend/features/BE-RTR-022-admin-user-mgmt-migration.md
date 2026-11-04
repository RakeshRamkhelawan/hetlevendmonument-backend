# BE-RTR-022 — Admin + User Management Domain Migration naar v1/

**Sprint:** SP-API-005 Dag 2
**Datum:** 2026-06-04
**Status:** DONE
**Commit:** b920aaab

---

## Overzicht

Twee flat-file endpoints gemigreerd naar ADR-033 drie-laags structuur:

1. `admin_endpoints.py` (606r) → `src/core/api/v1/admin/`
2. `user_management_endpoints.py` (829r) → `src/core/api/v1/user_management/`

---

## Bestanden

### v1/admin/

| Bestand | Inhoud |
|---------|--------|
| `__init__.py` | `domain_router` (geen prefix; sub-routers bevatten `/admin`) |
| `router.py` | Composite: include users_router + monitoring_router |
| `users_router.py` | POST /create_user, POST /assign_role/{user_id}, GET /users |
| `monitoring_router.py` | GET /dashboard, /system, /logs, /monitor, /public |
| `dependencies.py` | `require_admin_role`, `_resolve_tenant_id`, `_current_user_value` |

### v1/user_management/

| Bestand | Inhoud |
|---------|--------|
| `__init__.py` | `domain_router` (prefix=/api/v1) |
| `router.py` | Composite: include crud_router + profile_router |
| `crud_router.py` | POST /, GET /, GET /{user_id}, PUT /{user_id}, DELETE /{user_id}, POST /{user_id}/roles |
| `profile_router.py` | PUT /me, PATCH /{user_id}/status |
| `dependencies.py` | `require_admin` dependency |

---

## Registry-wijzigingen

- `registries/auth_admin.py`: vervangt `admin_endpoints.router` door `v1/admin.domain_router`
- `app_factory.py:94`: vervangt `user_management_endpoints.router` door `v1/user_management.domain_router`

---

## Tenant-isolatie analyse

- `admin_endpoints.py`: `getattr(user, "tenant_id", None)` patroon aanwezig in `_resolve_tenant_id()`.
  - In TESTING=1: tenant_id uit current_user (fail-secure: valt terug op `1` als None)
  - In productie: `require_tenant_id()` uit JWT/middleware (ADR-003 compliant)
- `user_management_endpoints.py`: `TenantFilterBypass` voor admin cross-tenant operaties (correct: admin kan alle tenants beheren)

---

## Kwaliteitsregels nageleefd

- `# orphan:exempt` op regel 1 van bestanden >200r (admin_endpoints.py, crud_router.py)
- Geen f-strings in logger (alle `%s` formatting)
- `exc_info=True` aanwezig bij alle exception handlers
- Geen `from __future__ import annotations`
- `src.core.database`/`governance` niet direct in router files (via dependencies.py)

---

## Trainingssamenvatting

### Flow 1 — Admin gebruiker aanmaken

| Stap | Detail |
|------|--------|
| **Actor** | Beheerder met admin-rol |
| **Voorwaarde** | JWT met admin/system_admin rol aanwezig; tenant_id beschikbaar |
| **Actie** | POST /admin/create_user met email + password + role |
| **Systeemverwerking** | tenant_id resolven → user aanmaken via auth_service → RBAC rol toewijzen → audit log |
| **Succesrespons** | HTTP 201 met user id, email, role, tenant_id |
| **Foutrespons** | HTTP 409 als email al bestaat; HTTP 403 als geen admin rol |
| **Uitzonderingen** | HTTP 500 bij DB-fout; audit log via log_security_event (niet best_effort hier) |

### Flow 2 — Gebruiker aanmaken via user_management

| Stap | Detail |
|------|--------|
| **Actor** | Beheerder met admin-rol |
| **Voorwaarde** | JWT met admin rol; target_tenant_id als query param |
| **Actie** | POST /api/v1/users/?target_tenant_id=1 met UserCreate body |
| **Systeemverwerking** | TenantFilterBypass → tenant check → email duplicate check → password hash → User ORM → rol toewijzing → audit via audit_service |
| **Succesrespons** | HTTP 201 met UserResponseSchema |
| **Foutrespons** | HTTP 404 als tenant niet bestaat; HTTP 400 als email al bestaat; HTTP 403 als geen admin |
| **Uitzonderingen** | Rol niet gevonden: skip met warning (geen fout); DB-rollback bij commit failure |

### Flow 3 — Eigen profiel bijwerken

| Stap | Detail |
|------|--------|
| **Actor** | Elke geauthenticeerde gebruiker |
| **Voorwaarde** | Geldig JWT |
| **Actie** | PUT /api/v1/users/me met optionele velden (email, full_name, password) |
| **Systeemverwerking** | User ophalen op current_user.id → alleen allowed_fields bijwerken → password hashing indien nodig → commit |
| **Succesrespons** | HTTP 200 met bijgewerkte UserResponseSchema |
| **Foutrespons** | HTTP 404 als user niet gevonden |
| **Uitzonderingen** | Geen audit log bij profiel-update (not business-critical) |

---

## Testresultaten

- 2 equivalentietests toegevoegd (test_admin_flat_file_migrated_to_v1, test_user_management_flat_file_migrated_to_v1)
- Beide tests: ROOD bevestigd voor implementatie, GROEN na implementatie
- Totaal: 144/144 PASS, 0 failed
