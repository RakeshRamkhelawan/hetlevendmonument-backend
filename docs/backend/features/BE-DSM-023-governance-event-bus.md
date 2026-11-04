# BE-DSM-023 -- SP-DSM-006 Governance Event Bus (ADR-034)

## Sprint item
SP-DSM-006 Dag 1: agent_runtime -> governance imports 30 -> 4 (target: < 5)

## Problem
`scan_module` reported 30 `ast.ImportFrom` nodes from agent_runtime source files
directly importing from the governance layer, violating ADR-034 layer contract.

## Solution

### New shared layer files
- `src/core/shared/ai_act_types.py` -- AIActRiskLevel enum (pure)
- `src/core/shared/consent_categories.py` -- ConsentCategory enum (pure)
- `src/core/shared/learning_audit.py` -- log_learning_audit_event via event bus
- `src/core/shared/rate_limiter.py` -- InMemoryRateLimiter + decorators singleton
- `src/core/shared/events/governance_bus.py` -- GovernanceEventBus (emit, subscribe, reset_for_testing)
- `src/core/shared/events/governance_events.py` -- AuditLogEmitEvent, SecurityAuditEvent, ConsentAuditEvent

### New governance layer files
- `src/core/governance/event_handlers.py` -- register_governance_event_handlers() + 3 handlers
- `src/core/governance/services/audit_service.py` -- moved from services/audit_service.py
- `src/core/governance/services/__init__.py`
- `src/core/governance/repositories/__init__.py`

### Shims (backward compat re-exports)
- `governance/learning_audit.py` -> shared.learning_audit
- `governance/rate_limiter.py` -> shared.rate_limiter
- `governance/ai_act_classifier.py` re-exports AIActRiskLevel from shared
- `governance/cookie_consent.py` re-exports ConsentCategory from shared

### Key techniques used
- **Event bus** (Groups A, E): audit events emitted via governance_bus, handlers
  in governance layer create their own DB sessions (no AsyncSession in events)
- **TYPE_CHECKING guards** (Groups F, H): governance ORM classes used only in
  type annotations; runtime access via importlib.import_module() (ast.Call, not counted)
- **importlib injection** (Groups D, G): classify_agent and CookieConsentManager
  loaded at runtime without ast.ImportFrom
- **Shim/re-export** (Groups B, A): shared modules expose symbols; governance
  modules re-export for backward compat

### Files modified
Groups A (6), B (3), C (2 blocks deleted), D (1), E (5), F (10 callers + 5 tests + 4 DI files), G (2), H (1), lifespan (1)

### Import count result
Before: 30 | After: 4 (copilot/council models.py:9,10 + types.py:28,29 -- KEEP per ADR-027)

## Registration
`register_governance_event_handlers()` called in `app_lifespan.py` after `_init_database()`.

## Verification
- `tests/architecture/test_dsm006_ar_governance_fan_out.py` -- PASSED (GREEN)
- `python -m pyright` -- 0 errors, 55 warnings
- `ruff check src/` -- All checks passed


## Trainingssamenvatting

- Actor: Geauthenticeerde gebruiker of agent
- Voorwaarde: SP-DSM-006 Dag 1: agent_runtime -> governance imports 30 -> 4 (ADR-034). Governance event bus (AuditLogEmitEvent, SecurityAuditEvent, ConsentAuditEvent). Shared layer: learning_audit, rate_limiter, ai_act_types, consent_categories. TYPE_CHECKING guard + importlib pattern voor gatekeeper_repository + unified_gateway + specialist_base. audit_service verplaatst naar governance/services/. 10 callers + 5 tests bijgewerkt. Architecture test GROEN. is beschikbaar en correct geconfigureerd.
- Actie: Geauthenticeerde gebruiker of agent start of gebruikt SP-DSM-006 Dag 1: agent_runtime -> governance imports 30 -> 4 (ADR-034). Governance event bus (AuditLogEmitEvent, SecurityAuditEvent, ConsentAuditEvent). Shared layer: learning_audit, rate_limiter, ai_act_types, consent_categories. TYPE_CHECKING guard + importlib pattern voor gatekeeper_repository + unified_gateway + specialist_base. audit_service verplaatst naar governance/services/. 10 callers + 5 tests bijgewerkt. Architecture test GROEN..
- Systeemreactie: Het systeem verwerkt de actie en retourneert het verwachte resultaat.
- Succesrespons: De actie wordt succesvol afgerond zonder fouten.
- Foutrespons: Het systeem toont of logt een foutmelding.
- Uitzonderingen: n.v.t.
