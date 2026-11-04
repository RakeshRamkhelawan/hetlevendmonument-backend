# BE-DSM-039 -- SP-DSM-018 Dag 1: auth/api_deps.py facade + Batch A (30 bestanden)

## Status

APPROVED

## Sprint

SP-DSM-018 Dag 1

## Datum

2026-06-26

## Doel

core_api Ce_excl_shared reduceren richting ≤800 (Grade A+) via auth-facade patroon.
Dag 1: facade aanmaken + Batch A top-30 bestanden migreren.

## Aanpak

### Nieuw bestand: `src/core/auth/api_deps.py`

Stable import point voor core_api laag (routers, endpoints).
Re-exporteert 26 auth-primitives uit 8 sub-modules.

Geexporteerde symbolen:
- `auth_service`: AuthService, UserCreate, UserResponse
- `dependencies`: CurrentUser, RequireAdmin, get_current_user, get_current_user_dependency, get_current_user_id, get_current_user_ws, get_optional_user_dependency, require_admin, require_permission
- `jwt_handler`: jwt_handler
- `permissions`: ADMIN_SCOPES, EDITOR_SCOPES, VIEWER_SCOPES
- `rbac`: Permission, RBACService
- `scope_validator`: has_scopes, require_scopes
- `scopes`: OAuth2Scope
- `types`: JWTPayload, VerifiedJWTPayload
- `websocket_auth`: AuthenticatedUser, WebSocketAuthenticator, get_ws_user, websocket_auth

### Batch A migratie (30 bestanden)

Patroon: N losse `from src.core.auth.<sub> import X` -> 1 `from src.core.auth.api_deps import X`.

Speciale gevallen:
- `auth/router_login.py`: alleen `get_current_user` + `OAuth2Scope` gemigreerd; `oauth2_service` + `account_lockout` blijven direct (buiten api_deps scope).
- `workflow_generation_router.py`: alleen top-level `get_current_user_dependency`; lazy `websocket_auth` imports in function bodies ongewijzigd.
- `monitoring_v1/dependencies.py`: `# noqa: F401 -- re-export` commentaar behouden.
- `users/dependencies.py`: `UserCreate as AuthUserCreate` alias behouden.

Gemigreerde bestanden (30 totaal):
1. src/core/api/v1/cva/management_router.py
2. src/core/api/v1/users/dependencies.py
3. src/core/api/v1/prediction/dependencies.py
4. src/core/api/v1/monitoring_v1/dependencies.py
5. src/core/api/v1/knowledge/search_router.py
6. src/core/api/v1/knowledge/crud_router.py
7. src/core/api/v1/knowledge/admin_router.py
8. src/core/api/v1/cva/public_router.py
9. src/core/api/v1/cva/chat_router.py
10. src/core/api/v1/autonomous/healing_router.py
11. src/core/api/v1/autonomous/emergence_router.py
12. src/core/api/v1/autonomous/code_router.py
13. src/core/api/v1/autonomous/agents_router.py
14. src/core/api/system_endpoints.py
15. src/core/api/monitoring_endpoints.py
16. src/core/api/knowledge_endpoints.py
17. src/core/api/autonomous_endpoints.py
18. src/core/api/auth/router_login.py
19. src/core/api/workflow_refinement_endpoints.py
20. src/core/api/v1/workflow/workflow_generation_router.py
21. src/core/api/v1/tool_broker/management_router.py
22. src/core/api/v1/tool_broker/execution_router.py
23. src/core/api/v1/tool_broker/crud_router.py
24. src/core/api/v1/subagents/router_management.py
25. src/core/api/v1/subagents/router_execution.py
26. src/core/api/v1/subagents/router_discovery.py
27. src/core/api/v1/sentiment_scanner/scanner_router.py
28. src/core/api/v1/security/dependencies.py
29. src/core/api/v1/production/reporting_router.py
30. src/core/api/v1/production/operations_router.py

## Meetresultaten

| Metriek | Voor | Na | Verschil |
|---------|------|----|---------|
| core_api->auth edges | ~450 | 375 | -75 |
| Pyright errors | 0 | 0 | 0 |
| Arch tests | 2 RED (verwacht) | 2 PASS | -- |

## Architecture Tests

Nieuw bestand: `tests/architecture/test_dsm018_api_deps_facade.py`

- `test_dsm018_api_deps_facade_exists`: facade bestaat -- PASS
- `test_dsm018_core_api_auth_ce_at_most_400`: core_api->auth 375 <= 400 -- PASS

## Scope

Volgende stap: SP-DSM-018 Dag 2 (Batch B: ~50 bestanden in src/core/api/v1/).

## Gerelateerde documenten

- Plan: C:\Users\rsram\.claude\plans\binary-baking-cake.md
- Arch test: tests/architecture/test_dsm018_api_deps_facade.py
- Facade: src/core/auth/api_deps.py


## Trainingssamenvatting

- Actor: Ontwikkelaar of QA
- Voorwaarde: SP-DSM-018 Dag 1: auth/api\_deps.py facade (26 re-exports) + Batch A 30 bestanden gemigreerd. core\_api->auth 450->375 (-75 edges). Pyright 0 errors. 2 arch-tests GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Ontwikkelaar of QA start of gebruikt SP-DSM-018 Dag 1: auth/api\_deps.py facade (26 re-exports) + Batch A 30 bestanden gemigreerd. core\_api->auth 450->375 (-75 edges). Pyright 0 errors. 2 arch-tests GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
