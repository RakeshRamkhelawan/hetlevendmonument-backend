# BE-TAUD-001 -- Tenant-scoped tool-audit read endpoint (BPA-009)

- Feature ID: BE-TAUD-001
- Status: Implemented
- Sprint: AGENTIC-COPILOT-TAAKBEHEER-2026-07 Dag 7
- Branch: `iter/dag7-gdpr`
- Reviewer: code-reviewer + security-reviewer (Gate 2) -- zie `docs/backend/review/review-BE-TAUD-001.md`
- Datum: 2026-07-13
- ADR: ADR-033 (3-laags router + dependencies facade), ADR-019 (audit), ADR-003 (tenant)

## Doel

De tool-audit-logboeken waren al DB-backed aan de schrijfkant (`ToolAuditRepository.log_execution` +
hash-chain), maar er was geen leesroute; het frontend-scherm las een lege store. BPA-009 (herijkt):
alleen het read-pad + FE-koppeling -- de write-kant NIET aangeraakt.

## Werk

- `ToolAuditRepository.get_logs(limit, offset)` + `count_logs()` (`src/core/tool_broker/audit_repository.py`)
  -- tenant-gescoped (`ToolAuditLog.tenant_id == self.tenant_id`), nieuwste eerst.
- ADR-033 3-laags module `src/core/api/v1/tool_audit/`: `dependencies.py` (facade `get_tool_audit_repo`,
  tenant uit JWT) + `router.py` (`GET /api/v1/tool-audit-logs`, admin-only, read-rate-limit).
  `router.py` importeert geen database/tool_broker direct (Contract 1; `TYPE_CHECKING` voor de repo-type).
- Geregistreerd in `src/core/api/registries/realtime.py`.

## Tenant-isolatie

De repository is tenant-gebonden via de constructor; alle leesmethoden filteren `self.tenant_id`.
Endpoint is admin-only (`_is_tenant_admin`).

## Acceptatiecriteria

- Admin krijgt de `tool_audit_logs` van de eigen tenant (paginering); niet-admin -> 403.
- Geen logs -> `{"success": true, "data": []}` (geen 500).
- Read-query filtert tenant_id (geen cross-tenant lek).

## Trainingssamenvatting

### Flow 1: Tool-audit-logboek opvragen

- Actor: tenant-admin.
- Voorwaarde: geauthenticeerd met admin-rol.
- Actie: `GET /api/v1/tool-audit-logs?limit=&offset=`.
- Systeemreactie: tenant-gescoopte read via `ToolAuditRepository.get_logs` + `count_logs`.
- Succesrespons: `{"success": true, "data": [...], "total": n}`.
- Foutrespons: niet-admin -> 403; geen data -> lege lijst (geen 500).
- Uitzonderingen: alleen leesroute; write-kant ongemoeid.

## Definition of Done

- [x] Repo-leesmethoden + ADR-033 endpoint + registratie; 4 unit tests groen
- [x] Frontend gekoppeld (zie FE-TAUD-001); Gate 3 groen; review APPROVED; ID-REGISTRY bijgewerkt
