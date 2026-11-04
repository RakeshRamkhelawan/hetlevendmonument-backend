# BE-GDPR-001 -- Admin-rol afgedwongen op tenant-brede delete-all (GDPR-001, P0)

- Feature ID: BE-GDPR-001
- Status: Implemented
- Sprint: AGENTIC-COPILOT-TAAKBEHEER-2026-07 Dag 8 (auth-kritiek)
- Branch: `iter/dag8-gdpr-authz`
- Reviewer: code-reviewer + security-reviewer (Gate 2) -- zie `docs/backend/review/review-BE-GDPR-001.md`
- Datum: 2026-07-13
- ADR: ADR-019 (audit), ADR-003/004/005 (tenant-isolatie), GDPR art. 17

## Doel / P0

`POST /api/gdpr/delete-all` (`src/core/api/v1/gdpr_compliance/erasure_router.py`) wist de HELE tenant.
De HARD-tak checkte de admin-rol, de **SOFT-tak niet** -- de enige gate was `confirmation_code ==
tenant_id`, en `tenant_id` komt uit de JWT (geen geheim). Gevolg (P0, actief exploiteerbaar op develop):
een niet-admin tenant-member kon de hele tenant soft-deleten (users/agents/workflows) + een hard purge
inplannen. Privilege-escalatie binnen de tenant.

## Fix

De admin-check (`"admin" in current_user.roles`, uit de geverifieerde JWT -- nooit body/param) staat nu
VOOR de SOFT/HARD-vertakking, zodat een tenant-brede erasure altijd admin vereist. `confirmation_code`
blijft een UX-safeguard. De bestaande ADR-019 audit-entry (`AuditService.log_action`, best_effort) blijft.

## Delete-endpoint inventaris (authz-conclusie)

De gap-analyse (Explore, 2026-07-13) inventariseerde alle destructieve endpoints. **Gewijzigd in deze diff:**
alleen `erasure_router.delete_tenant_data`. De overige delete-endpoints zijn in die gap-analyse als
JWT-afgeleid + owner/admin/superuser-gecontroleerd beoordeeld -- **niet opnieuw geverifieerd binnen deze
diff** (buiten de twee gewijzigde commits): `analytics_ingest/gdpr_router` `/events/user` (self, JWT-sub),
`analytics_endpoints` `/events/user` (self), `privacy/dsar_router` `/forget` (self), `admin_learning`
`/gdpr/delete-user` (`require_admin_role`), `users_detail_router` DELETE (superuser/can_manage_users),
`tenants_detail_router` DELETE (superuser), `cva/conversations_router` DELETE (self/tenant via CVAService).
De DSAR-servicelaag (`dsar_service.py` `_authorize` + hard-delete-admin-gate) is correct en NIET herbouwd.

## Acceptatiecriteria

- Non-admin SOFT delete-all -> 403 (P0 dicht); non-admin HARD -> 403; admin SOFT/HARD -> happy.
- `is_admin` uit de JWT-rol, nooit uit body/param (confirmation_code is geen authz-hefboom).
- Alle delete-queries tenant-scoped op de JWT-tenant (bound-value getest, SOFT + HARD).

## Trainingssamenvatting

### Flow 1: Tenant-brede data-erasure

- Actor: tenant-admin (rol uit de geverifieerde JWT).
- Voorwaarde: `confirmation_code == tenant_id` en admin-rol.
- Actie: `POST /api/gdpr/delete-all` (SOFT of HARD).
- Systeemreactie: admin-check VOOR de vertakking; daarna soft-markering of harde delete; ADR-019 audit-entry.
- Succesrespons: `DeleteDataResponse` met records_deleted/categories.
- Foutrespons: geen admin-rol -> 403; verkeerde confirmation_code -> 400.
- Uitzonderingen: cross-tenant onmogelijk (tenant uit JWT); non-admin kan niets wissen of purgen.

## Definition of Done

- [x] Admin-gate voor SOFT + HARD; 6 unit tests groen (incl. P0-rode-test + DSAR-regressie)
- [x] Gate 2 code + security APPROVED; Gate 3 ruff 0 / pyright 0; ID-REGISTRY bijgewerkt
