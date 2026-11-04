# Backend Feature Specification

## Metadata

- Feature ID: BE-PRANA-001
- Naam: Department prana-economie (ADR-021) productie-live
- Status: Implemented (flag-guarded, default OFF)
- Auteur: Claude (prana-economy sprint)
- Reviewer: code-reviewer (GO) + security-reviewer (GO) -- fase 1 + fase 3
- Datum: 2026-07-16
- ADR: ADR-021 (prana economy), ADR-005 (tenant_id NOT NULL + RLS), ADR-019 (hash-chain), ADR-004 (auto-WHERE), ADR-027 (Council)

## Doel en scope

Een echte, persistente, tenant-veilige prana-economie: elke tenant heeft per department
een budget (10.000, ADR-021); Council-goedgekeurde copilot-acties en ALS-specialist-stappen
worden atomair belast; budgetten resetten dagelijks; een op-raken-budget blokkeert verdere
acties (auto-block). Vervangt drie losse, inconsistente, niet-persistente implementaties.

### In scope
- Persistente modellen `PranaDepartmentBudget` + append-only `PranaTransaction` (per-(tenant,
  department) SHA-256 hash-chain) + Alembic-migratie met RLS.
- `PranaService`: atomaire `charge` (conditionele UPDATE + rowcount, enige gate), `refund`,
  `refill_all` (TenantFilterBypass), `allocate_emergency` (authorized_by-guard), advisory
  fail-closed `has_budget`, `provision_tenant`, agent-type `tier`-prijzen, grace-floor.
- Enforcement bedraad (flag-guarded, `PRANA_ENFORCEMENT_ENABLED` default OFF): Council
  ResourceOfficer-adapter + charge-hook in `CopilotService._execute_decision` (charge vóór
  executie + refund bij falen) + PranaGuard-consolidatie voor ALS `specialist_base`.
- Provisioning bij tenant-aanmaak (beide create-paden) + backfill-migratie bestaande tenants.
- Dagelijkse refill Dramatiq-actor + scheduler-registratie (idempotente reset).
- REST: `GET /api/v1/prana/budgets` (PRANA_READ) + `POST /api/v1/prana/allocate` (PRANA_MANAGE);
  frontend department-budget-view + emergency-allocatie.

### Out of scope
- WE-021 (TaskScheduler in een eigen container/lifespan starten) -- de refill-job is
  geregistreerd, maar de scheduler-boot is een aparte infra-klus.
- `<10%` alert-notificatie-dispatch (vereist de dag-7 notificatie-service) -- gedocumenteerde
  follow-up; auto-block bij 0 is wel actief.
- De A2A agent-ledger (`/prana/balance`, `/prana/ledger`) blijft een apart subsysteem.

## Veiligheids-/rollout-model

`PRANA_ENFORCEMENT_ENABLED` (default OFF): OFF -> `has_budget` True, geen charge, PranaGuard
no-op -> GEEN copilot-gedragswijziging. ON -> volledige economie. Uitrolvolgorde: deploy met
flag OFF, provisioning-backfill draaien, dan flag ON (prod, expliciete stap). Department voor
copilot is server-side vast (CUSTOMER_EXPERIENCE) -- nooit uit LLM-`action_params`
(budget-shopping uitgesloten). Enforcement-gate is de atomaire conditionele UPDATE
(race-vrij, fail-closed); emergency-allocatie achter PRANA_MANAGE met een verified caller-id.

## Verificatie

- Unit + integratie: `pytest tests/unit/governance tests/integration/governance/test_prana_service_integration.py`
  (incl. echte 2-connectie concurrency-test: geen oversell/negatief; full economy lifecycle).
- Arch: `tests/architecture/test_prana_emergency_scope_gated.py` (PRANA_MANAGE-gate) +
  `test_scoped_broker_is_tracked.py`.
- pyright/ruff 0 op de prana-bestanden; `alembic heads` = 1.

## Trainingssamenvatting

### Flow 1: Copilot-actie belast het department-budget (enforcement ON)

- Actor: ingelogde tenant-gebruiker via de Copilot-chat.
- Voorwaarde: `PRANA_ENFORCEMENT_ENABLED=true`, tenant heeft geprovisioneerde budgetten.
- Actie: verzendt een taakverzoek; de Council keurt de actie goed.
- Systeemreactie: vóór executie wordt het CUSTOMER_EXPERIENCE-budget atomair belast met de
  actie-kosten; de actie voert uit; een hash-chained transactie wordt vastgelegd.
- Succesrespons: actie uitgevoerd, budget verlaagd, ledger-entry aangemaakt.
- Foutrespons: onvoldoende budget -> actie wordt NIET uitgevoerd (auto-block), turn meldt
  budget-uitputting; executie-fout na charge -> refund.
- Uitzonderingen: enforcement OFF -> geen charge (copilot ongewijzigd); department nooit uit
  user-input.

### Flow 2: Emergency-allocatie door een beheerder

- Actor: beheerder/developer met de `prana:manage`-scope.
- Voorwaarde: authenticatie met PRANA_MANAGE.
- Actie: `POST /api/v1/prana/allocate` met department + bedrag + reden.
- Systeemreactie: het department-budget wordt verhoogd; een emergency-ledger-entry legt actor
  + reden vast.
- Succesrespons: `{"success": true, "balance_after": ...}`.
- Foutrespons: ontbrekend budget -> 404; zonder PRANA_MANAGE -> 403.
- Uitzonderingen: `authorized_by` is altijd de geverifieerde caller-id, nooit client-input.

## Definition of Done

- [x] Modellen + migratie (RLS, downgrade, heads=1)
- [x] PranaService (atomair, fail-closed, hash-chain) + provisioning + refill + emergency
- [x] Enforcement flag-guarded bedraad (copilot + ALS)
- [x] REST + scopes + frontend
- [x] Gate-2 code + security GO (fase 1 + fase 3), minors verwerkt
- [x] pyright/ruff 0; prana-tests groen
- [ ] Rollout-flip naar ON in prod -- Rakesh-beslissing na provisioning-backfill + Key Vault
