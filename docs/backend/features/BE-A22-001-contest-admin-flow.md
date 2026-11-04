# BE-A22-001 -- Contest admin-flow (GDPR art. 22)

- Feature ID: BE-A22-001
- Status: Implemented
- Sprint: AGENTIC-COPILOT-TAAKBEHEER-2026-07 Dag 7
- Branch: `iter/dag7-gdpr`
- Reviewer: code-reviewer + security-reviewer (Gate 2) -- zie `docs/backend/review/review-BE-A22-001.md`
- Datum: 2026-07-13
- ADR: ADR-019 (audit hash-chain), ADR-027 (Council), ADR-031 (governance/AI Act), ADR-003/004 (tenant)

## Doel

Een tenant-admin kan ingediende bezwaren tegen AI-beslissingen (GDPR art. 22) inzien en afhandelen.
Voorheen bestond alleen het aanmaak-endpoint; de queue, resolve en echte notificatie ontbraken.

## Endpoints (`src/core/copilot/api/audit_endpoints.py`)

- `GET /api/v1/copilot/audit/contests` -- admin-only queue (`_is_tenant_admin`), tenant-gescoped op
  `DecisionContestRow.tenant_id`, paginering `limit`/`offset`, read-rate-limit. Response
  `{"success": true, "data": [...], "total": n}`.
- `POST /api/v1/copilot/audit/contests/{contest_id}/resolve` -- admin + tenant-ownership; zet
  `status` (`upheld`/`overturned`), `resolution_text`, `resolved_at`, `resolver_user_id`.
  Idempotent: al-geresolved -> 409. Onbekend/andere tenant -> 404 met identieke message (geen enumeratie).

## Notificatie + audit

- Resolve schrijft een echte `Notification`-rij voor de indiener (`contest.user_id`) via `best_effort`.
- Resolve schrijft een ADR-019 hash-chained audit-entry via `AuditService.log_action`
  (action `contest_resolved`, tamper-evident).

## Tenant-isolatie

Elke query filtert `tenant_id` uit het JWT (`require_tenant_id`), nooit uit de body. `ContestResolveRequest`
bevat alleen `status` + `resolution_text`.

## Acceptatiecriteria

- Admin ziet alleen contests van de eigen tenant; niet-admin -> 403.
- Resolve zet de vier resolve-velden; al-geresolved -> 409; onbekend id -> 404.
- Indiener krijgt een echte Notification; resolve schrijft een gehashte audit-entry.

## Openstaand (gedocumenteerde follow-up)

Admin-fan-out bij een *nieuwe* contest (`contest_service.py` dramatiq-stub) is niet omgezet naar echte
inserts: het mechanisme om alle tenant-admins op te sommen (`User.roles`) is niet eenduidig; niet gegokt.
De hoge-waarde notificatie (indiener bij resolve) is wel echt.

## Trainingssamenvatting

### Flow 1: Bezwaar afhandelen als admin

- Actor: tenant-admin.
- Voorwaarde: er bestaat een `pending` contest binnen de eigen tenant.
- Actie: POST resolve met `status` + `resolution_text`.
- Systeemreactie: contest krijgt status/resolution/resolved_at/resolver_user_id; indiener krijgt een
  Notification; een hash-chained audit-entry wordt geschreven.
- Succesrespons: `{"success": true, "contest_id": ..., "status": ...}`.
- Foutrespons: niet-admin -> 403; al-geresolved -> 409; onbekend/andere-tenant id -> 404.
- Uitzonderingen: tenant nooit uit body; cross-tenant 404 identiek (geen enumeratie).

## Definition of Done

- [x] Endpoints + notify + audit geimplementeerd; 9 unit tests groen
- [x] Gate 2 (code + security) -- blocker (ADR-019 audit) opgelost
- [x] Gate 3: ruff 0, pyright 0; review APPROVED; ID-REGISTRY bijgewerkt
