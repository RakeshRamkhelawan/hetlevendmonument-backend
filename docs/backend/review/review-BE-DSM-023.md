# Review BE-DSM-023 -- SP-DSM-006 Governance Event Bus

**Reviewer:** code-reviewer + quality-reviewer (Gate 2 rev 5)
**Sprint:** SP-DSM-006
**Status:** APPROVED

---

## Code Review (architecture + ADR compliance)

### APPROVED items

- **ADR-034 compliance**: agent_runtime -> governance imports reduced 30 -> 4.
  Remaining 4 are copilot/council/{models,types}.py -> governance.models, intentionally
  retained per ADR-027 (council models are dual-layer by design).

- **Event bus design**: GovernanceEventBus uses asyncio pub/sub. Handlers in the
  governance layer open their own DB sessions via `db_manager.async_session_maker()`,
  keeping event dataclasses free of AsyncSession (stdlib types only). Correct.

- **best_effort wrapping**: All audit event emissions wrapped in `async with best_effort(...)`.
  Primary operations (role assign, consent grant, etc.) unaffected by audit failures.

- **TYPE_CHECKING guard pattern**: gatekeeper_repository.py uses `_governance_cls()`
  importlib helper. Return type annotated under TYPE_CHECKING for pyright safety.
  `# type: ignore[return-value]` is narrow and justified.

- **`from __future__ import annotations`**: Used only where TYPE_CHECKING-guarded
  names appear in function signatures (gatekeeper_repository.py). Correct usage.

- **DI injection**: gdpr_service.py defaults to `[]` when no reader injected (safe).
  unified_gateway.py annotates `self.ethics_gate: Any` (avoids None-attribute pyright error).

- **audit_service.py move**: Deleted from services/, recreated in governance/services/.
  10 callers updated. 5 test files updated. Import path is now intra-governance.

- **`register_governance_event_handlers()`**: Wired in app_lifespan.py after
  `_init_database()`. Order is correct (db must be up before handlers can open sessions).

### No CRITICAL or HIGH findings.

---

## Quality Review (ruff + pyright + security)

- **pyright**: 0 errors, 55 warnings (baseline maintained, commit b1398e4c).
- **ruff**: All checks passed.
- **mypy**: Not run (pyright is the enforced tool per CLAUDE.md Gate 3).
- **Security**: No new tenant_id from request body. No datetime.now() calls introduced.
  No secrets in new files.
- **OWASP**: audit_service.py move does not change security surface. Event handlers
  create sessions correctly (no session passed in events).

### No CRITICAL or HIGH findings.

---

## Verdict

**APPROVED FOR MERGE** (develop branch, per HITL gate -- Rakesh GO required for main).

Architecture test `test_agent_runtime_governance_coupling_below_5` is GREEN.
Unit suite: 865+/875 pass (pre-existing baseline).
