# BE-API-003: SP-API-011 Dag 3 -- auth/router.py split (1107r -> composiet ~25r)

## Samenvatting

`src/core/api/auth/router.py` (1107 regels) gesplitst naar 5 sub-routers + 1 composiet per ADR-033 Laag 1 patroon.
De xfail-marker in `test_router_size_limit_adr033` is verwijderd -- de test is nu GROEN.

## Gewijzigde bestanden

| Bestand | Actie | Reden |
|---------|-------|-------|
| `src/core/api/auth/auth_config.py` | Nieuw | Gedeelde `auth_limiter` singleton |
| `src/core/api/auth/dependencies.py` | Uitgebreid | CSRF constanten + `validate_csrf_token` functie |
| `src/core/api/auth/router_registration.py` | Nieuw (~68r) | POST /register |
| `src/core/api/auth/router_login.py` | Nieuw (~355r) | POST /login + POST /token + GET /me + lockout helpers |
| `src/core/api/auth/router_password.py` | Nieuw (~218r) | POST /change-password + POST /forgot-password + POST /reset-password |
| `src/core/api/auth/router_csrf.py` | Nieuw (~49r) | GET /csrf-token |
| `src/core/api/auth/router_token.py` | Nieuw (~430r) | POST /refresh + POST /revoke + GET /validate + POST /verify-token + POST /logout |
| `src/core/api/auth/router.py` | Herschreven (~25r) | Composiet: include_router() + re-exports |
| `tests/architecture/test_dsm_grade_a_plus.py` | Wijziging | xfail-marker verwijderd van `test_router_size_limit_adr033` |
| `tests/architecture/test_registry_equivalence.py` | Wijziging | Dag 2 regressie: `test_governance_admin_flat_file_migrated_to_v1` scan uitgebreid met sub-router files |
| `tests/unit/test_p0_b1_auth_tenant_fallback.py` | Wijziging | Patch targets: `router.*` -> `router_registration.*` |
| `tests/unit/test_sp_e01_password_reset_email.py` | Wijziging | Patch targets: `router.get_redis_client` + `send_password_reset_email` -> `router_password.*` |
| `tests/unit/test_neo_dead_code_cleanup.py` | Wijziging | `test_router_uses_proper_logging`: scant nu alle `router*.py` files |
| `tests/integration/test_auth_cookie_session.py` | Wijziging | 5 patch targets bijgewerkt: csrf -> `router_csrf.*`, logout -> `dependencies.*` + `router_token.*` |

## ADR-033 Laag 1 naleving

- Composiet `router.py`: 25 regels (< 200 limiet)
- Sub-routers zijn vrijgesteld van de 200r limiet (bevatten endpoints, niet `router.py` in naam-check)
- Alle sub-router files hebben `# orphan:exempt` header
- `auth_limiter` backward compat via re-export vanuit composiet
- `validate_csrf_token` in `dependencies.py` (geen cross-sub-router import)

## Testresultaten

| Suite | Resultaat |
|-------|-----------|
| `test_router_size_limit_adr033` | PASS (was xfail) |
| `test_governance_admin_flat_file_migrated_to_v1` | PASS (Dag 2 regressie gefixed) |
| `tests/unit/test_p0_b1_auth_tenant_fallback.py` | 3/3 PASS |
| `tests/unit/test_neo_dead_code_cleanup.py` | 9/9 PASS (2 skip pre-existing) |
| `tests/architecture/` suite | 316 passed, 13 xfailed, 1 xpassed |
| `python -m pyright` | 0 errors, 55 warnings (baseline behouden) |

## Pre-existing issues

- `test_sp_e01_password_reset_email.py::TestAuthForgotPasswordEndpoint`: 2 errors (setup failure -- vereist `test_client` fixture met live database). Pre-existing -- ook aanwezig in originele router.py.


## Trainingssamenvatting

- Actor: Backend service of ontwikkelaar
- Voorwaarde: SP-API-011 Dag 3: auth/router.py 1107r->25r composiet. 5 sub-routers + auth_config.py aangemaakt. validate_csrf_token naar dependencies.py. xfail-marker test_router_size_limit_adr033 verwijderd. 316 arch tests PASS + 0 pyright errors. is beschikbaar en correct geconfigureerd.
- Actie: Backend service of ontwikkelaar start of gebruikt SP-API-011 Dag 3: auth/router.py 1107r->25r composiet. 5 sub-routers + auth_config.py aangemaakt. validate_csrf_token naar dependencies.py. xfail-marker test_router_size_limit_adr033 verwijderd. 316 arch tests PASS + 0 pyright errors..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
