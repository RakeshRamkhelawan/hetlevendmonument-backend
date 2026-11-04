# Review BE-WFL-004 -- RouterAgentService tenant_id propagatie

**Reviewer:** Code Agent + Quality Agent (Gate 2, SP-ADR023-DAG2)
**Status:** APPROVED
**Datum:** 2026-06-27

---

## Bevindingen

### Correctheid

- `execute_request(query, tenant_id=None)` -- optionele parameter, backward-compatible.
- Return-dict bevat `"tenant_id": tenant_id` -- additief veld, geen breaking change.
- `_execute_step(step, tenant_id=None)` -- doorgeeft aan `execute_request(query, tenant_id=tenant_id)`.
- `execute_workflow()` threadt `workflow.tenant_id` naar elk step via `_execute_step(step, workflow.tenant_id)`.
- Type `str | None` -- correct voor DDD-laag; systeem-brede `ContextVar[int]` niet geraakt.

### Security

- Geen `tenant_id` uit request body.
- `tenant_id` vloeit van `workflow.tenant_id` (intern DDD-object) naar LLM-aanroep context.
- Geen hardcoded secrets.

### Tests

- 2 nieuwe RED tests (commit `4821c115`) GROEN na fix -- correct TDD-patroon.
- 8 tests totaal -- allemaal GROEN.
- 384 bestaande agent-tests ongewijzigd GROEN.

### Kwaliteit

- pyright: 0 errors (baseline gehandhaafd).
- ruff: 0 nieuwe errors.
- Geen emoji, geen non-ASCII.

### Pre-existing issues (niet in scope)

- `RouterAgentService` f-string logging zonder stack trace (pre-existing, niet geintroduceerd).
- Per-tenant LLM-credentials: aparte sprint.

---

## FA-review bevindingen (GO WITH MINOR ISSUES -- 2026-06-27)

Na FA-review zijn 4 minors direct gefixed in commit `f3d98b13`:

- FA-001: f-string logging -> `%s + exc_info=True` (6 calls in `router_agent_service.py`)
- FA-002: mock return_value dicts bijgewerkt met `"tenant_id"` key
- FA-003: `test_execute_step_forwards_none_tenant_id_when_not_provided` toegevoegd (9e test)
- FA-006: BE-WFL-004 spec claim gecorrigeerd

Test suite na minors-fix: 9/9 GROEN. pyright 0 errors. ruff clean.

## Conclusie

**APPROVED** -- tenant_id threading compleet. Backward-compatible. 9 tests groen. FA-minors gefixed.
