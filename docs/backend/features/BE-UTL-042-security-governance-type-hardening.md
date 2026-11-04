# BE-UTL-042 — Security & Governance Type-Hardening

## Overzicht

Cross-cutting type-hardening van de meest risicovolle security/governance grenzen:
auth, JWT, tenant isolatie, middleware en RLS validatie. Vervangt `Any` annotaties
door concrete `TypedDict`s, `Protocol`s en generieke types.

## ID

- **ID:** BE-UTL-042
- **Sprint:** SP-TYPE-006 — Type-Hardening Sprint 1 — Security & Governance Boundaries
- **Status:** In progress

## Gewijzigde componenten

| Bestand | Wijziging |
| ------- | --------- |
| `src/core/auth/types.py` | `JWTPayload`, `VerifiedJWTPayload` TypedDicts (uitgebreid met `role`, `username`, `fresh`, `type`, `token_type`) |
| `src/core/auth/scope_validator.py` | `list[str]` scopes, `_LegacyUserPermissionService` Protocol, `Coroutine[None,None,int]` return type |
| `src/core/auth/oauth2_service.py` | `list[int]` role_ids, `list[str]` scopes, `JWTPayload`, `VerifiedJWTPayload` |
| `src/core/auth/jwt_handler.py` | `JWTPayload` create input, `VerifiedJWTPayload | None` verify output |
| `src/core/auth/auth_bearer.py` | `AsyncSession` + `UserResponse` types |
| `src/core/auth/websocket_auth.py` | `VerifiedJWTPayload` payload input, `list[str]` roles |
| `src/core/security/security_manager.py` | `VerifiedJWTPayload | None` verify output |
| `src/core/middleware/tenant_middleware.py` | `list[str]` scopes, `VerifiedJWTPayload` via `verify_token` retourtype |
| `src/core/security/types.py` | Nieuw: `HasTenantId` Protocol (naast bestaande enums) |
| `src/core/security/rls_validation.py` | `HasTenantId | None`, `Sequence[HasTenantId | None]`, `Select[Any]` |
| `src/core/middleware/tenant_context.py` | `_detect_injection_in_value(object)`, `dict[str, str \| bool \| int \| None]` |
| `src/core/api/dependencies.py` | `JWTPayload` casts in legacy wrappers |
| `src/core/security/__init__.py` | `JWTPayload` cast in deprecated wrapper, ASCII-only cleanup |

## Tests

- `tests/unit/auth/test_types.py`
- `tests/unit/auth/test_oauth2_service.py`
- `tests/unit/auth/test_scope_validator.py`
- `tests/unit/middleware/test_tenant_middleware_types.py`
- `tests/unit/security/test_rls_validation_types.py`
- `tests/unit/middleware/test_tenant_context_types.py`
- `tests/unit/auth/test_jwt_handler_types.py`
- `tests/unit/auth/test_auth_bearer_types.py`
- `tests/unit/security/test_security_manager_types.py`
- `tests/unit/auth/test_websocket_auth_types.py`

## Definition of Done

- [x] Geen nieuwe ruff errors
- [x] Geen nieuwe pyright errors in gewijzigde files
- [x] Geen nieuwe mypy errors in gewijzigde files
- [x] Affected tests groen
- [ ] Review door onafhankelijke subagent (gepland dag 5)
- [x] ID-REGISTRY bijgewerkt

## Trainingssamenvatting

- Actor: Ontwikkelaar of SecurityOfficer
