# Subagent Code Review — SP-FB-001 FocusBuilder P0-fixes

## Scope

Files reviewed:

- `src/domains/flows/service.py`
- `src/domains/flows/repository.py`
- `src/core/focus_builder/models.py`
- `src/core/focus_builder/repositories.py`
- `src/core/database/model_registry.py`
- `src/core/api/v1/focus_builder/flows_router.py`
- `src/core/api/v1/focus_builder/pieces_router.py`
- `src/alembic/versions/20260618_add_focus_builder_tables.py`
- `tests/unit/domains/flows/test_service.py`
- `tests/unit/domains/flows/test_repository.py`
- `tests/integration/test_focus_builder_smoke.py`
- `tests/integration/test_focus_builder_phase4.py`

## Summary verdict

**REQUEST CHANGES**

The active FocusBuilder paths (`src.domains.flows.*`) correctly implement the three P0 fixes: lazy `ActivePiecesClient`, DB-first `create_flow`, and `flush()`-only repository writes. The Alembic migration creates the canonical `flows` and `focus_builder_pieces_cache` tables with RLS.

However, the change set still carries legacy `FocusBuilderFlow` / `src.core.focus_builder.repositories.FlowRepository` code that points to a `focus_builder_flows` table which the migration does **not** create. That code is registered in `model_registry.py` / `import_all_models.py`, so `Base.metadata` contains a production-nonexistent table and the Phase 4 integration tests exercise this dead code against a test-only table. This is a schema drift / false-confidence issue that must be resolved before the sprint can be considered safe for production.

Additional blockers: the `PUT /flows/{id}` endpoint silently drops non-graph fields when a graph is supplied, and integration tests do not mirror the production RLS policy on `flows`.

---

## Per-file findings

### `src/core/focus_builder/models.py`

#### HIGH — `FocusBuilderFlow` maps to a table the migration never creates

- **Line 18**: `__tablename__ = "focus_builder_flows"`.
- The migration `20260618_add_focus_builder_tables.py` only creates `flows` and `focus_builder_pieces_cache`. It does **not** create `focus_builder_flows`.
- Because `src.core.database.model_registry` and `src.core.database.import_all_models` still import this module, `Base.metadata` contains `focus_builder_flows`. The integration-test `create_all` therefore creates it, but an Alembic-upgraded production database will not.
- Any future import/use of `src.core.focus_builder.repositories.FlowRepository` or `src.core.focus_builder.service.FocusBuilderService` in production will fail with `relation "focus_builder_flows" does not exist`.
- The feature spec explicitly out-of-scopes full removal of `FocusBuilderFlow`, but leaving it registered in the canonical model registry creates a test/production schema drift. At minimum it must be removed from `model_registry.py` / `import_all_models.py`, or the migration must create the table.

#### MEDIUM — `version` column present but unused by canonical service

- **Line 37**: adds an optimistic-locking `version` column.
- The canonical service (`src.domains.flows.service.FocusBuilderService`) and repository (`src.domains.flows.repository.FlowRepository`) do not use this column. It only surfaces in the legacy `src.core.focus_builder.repositories.FlowRepository`.
- This is not a bug by itself, but it contributes to the confusion between the two parallel implementations.

---

### `src/core/focus_builder/repositories.py`

#### HIGH — `FlowRepository` operates on a production-nonexistent table

- **Line 9**: imports `FocusBuilderFlow` from `src.core.focus_builder.models` (table `focus_builder_flows`).
- **Lines 20-240**: `FlowRepository` provides CRUD/batch operations against `FocusBuilderFlow`.
- This repository is not used by any ADR-033 router (routers depend on `src.domains.flows.service.FocusBuilderService`, which uses `src.domains.flows.repository.FlowRepository`). It is therefore dead code in production paths, and the tests that cover it (`tests/integration/test_focus_builder_phase4.py`) pass only because the test harness creates the legacy table via `Base.metadata.create_all`.
- **Recommendation**: remove `FlowRepository` from this file (keeping only `PiecesRepository`), or migrate it to use the canonical `Flow` model and `flows` table.

#### MEDIUM — `PiecesRepository` cache layer serializes incomplete objects

- **Lines 354-365**: `_cache_pieces` stores only `id`, `piece_name`, `display_name`, `logo_url`, `actions`, `triggers`.
- **Lines 338-341**: `_get_cached_pieces` reconstructs `FocusBuilderPieceCache(...)` ORM objects from those cached dicts, dropping `description`, `auth_config`, `piece_version`, and `last_synced_at`.
- A cache hit therefore returns materially different data than a DB hit. If this repository were ever used for the schema endpoint, the response would be incomplete.
- **Recommendation**: either cache the full dict representation or stop reconstructing ORM objects from cache and return plain dataclasses/dicts.

#### MEDIUM — `batch_delete` / `batch_update_status` take a `tenant_id` parameter that overrides `self._tenant_id`

- **Lines 190-210, 212-239**: both methods accept `tenant_id: int` and use it instead of `self._tenant_id`.
- This weakens the repository's tenant-scoping contract and creates a foot-gun for callers. Internal batch methods should rely on the repository's injected tenant.
- **Recommendation**: remove the `tenant_id` parameter and use `self._tenant_id` consistently.

#### LOW — unnecessary `builtins.list` annotations

- **Lines 10, 170, 190, 212**: `import builtins` and `builtins.list[...]` are used where the plain `list[...]` builtin would work.
- **Recommendation**: remove the `builtins` import and use standard `list` annotations.

#### LOW — unused `Optional` import

- **Line 1**: `from typing import ... Optional` is imported but the file uses `| None` syntax everywhere.

---

### `src/core/database/model_registry.py`

#### HIGH — registry still imports `FocusBuilderFlow`, polluting `Base.metadata`

- **Lines 97-102**: registers `("core.focus_builder", "src.core.focus_builder.models", ["FocusBuilderFlow"])`.
- As noted above, this causes `Base.metadata` to include `focus_builder_flows`, which the SP-FB-001 migration does not create. Alembic autogenerate will therefore propose a second `focus_builder_flows` table, and the integration tests create a table that production lacks.
- The feature spec says removal of `FocusBuilderPieceCache` from the registry was in scope; it says nothing about keeping `FocusBuilderFlow` in the registry. Because `FocusBuilderFlow` is legacy and its table is not migrated, it should not be registered here.
- **Recommendation**: remove the `core.focus_builder` group from `_MODEL_GROUPS` until a migration exists for `focus_builder_flows` or the model is deleted entirely.

---

### `src/domains/flows/service.py`

#### HIGH — `update_flow` path in router drops non-graph fields when graph is supplied

- The router (`src/core/api/v1/focus_builder/flows_router.py`, lines 152-158) branches:
  - if `flow_in.react_flow_graph` is supplied → calls `service.update_flow(flow_id, flow_in.react_flow_graph)`;
  - else → calls `service.repository.update(flow_id, flow_in.model_dump(exclude_unset=True))`.
- **Line 103-141**: `FocusBuilderService.update_flow` only accepts a `graph` parameter and updates `react_flow_graph`, `activepieces_flow_json`, and `activepieces_version`. It never touches `name`, `description`, or `is_published`.
- Result: a request that updates both the graph and the name/description/published flag will silently lose the non-graph changes. This is a real user-visible regression.
- **Recommendation**: change `service.update_flow` to accept the full `FlowUpdate` schema, or always route updates through the repository after validating/compiling the graph.

#### MEDIUM — `update_flow` is not gracefully degrading on ActivePieces failure

- **Lines 122-127**: any exception during the AP update is converted to `ValueError("Failed to update flow in ActivePieces: ...")` and propagated, so the DB update is **not** persisted.
- This is inconsistent with `create_flow` (lines 65-99), which logs the AP error and returns the locally persisted flow.
- **Recommendation**: align `update_flow` with `create_flow`: save to DB first, then attempt AP sync, and keep the DB changes even if AP fails.

#### MEDIUM — uses deprecated Pydantic v1 `.dict()` method

- **Lines 48, 113**: `graph.dict()`.
- The project stack is Pydantic v2 (`AGENTS.md`). The correct method is `.model_dump()`. `.dict()` still works but is deprecated and may be removed.
- **Recommendation**: replace both occurrences with `graph.model_dump()`.

#### MEDIUM — calls private method on `ActivePiecesClient`

- **Line 246**: `return await self.ap_client._find_project_for_tenant(self.tenant_id)`.
- A service should not depend on a private helper of a client. If the lookup is part of the public contract, expose it as a public method.
- **Recommendation**: rename `_find_project_for_tenant` to `find_project_for_tenant` in `src/core/activepieces/client.py` and update the call site.

#### LOW — `description` from `FlowCreate` is ignored

- **Lines 35-62**: `create_flow` signature is `(name, graph, created_by)`; it never receives or stores `description`.
- The Pydantic `FlowCreate` schema includes `description`, so the API accepts it but it is silently discarded.
- **Recommendation**: pass `description` into the repository `create` call.

#### LOW — error messages may leak internal transformer exceptions

- **Lines 49, 115**: `raise ValueError(f"Invalid Flow Graph: {str(e)}")`.
- Internal transformer failure details are forwarded to the API caller. While not a security breach on its own, it violates the principle of least disclosure and makes the API surface dependent on internal exception text.
- **Recommendation**: log the full exception internally and return a generic validation message to the client.

---

### `src/domains/flows/repository.py`

#### MEDIUM — `update` uses `hasattr` / `setattr` loop over arbitrary keys

- **Lines 66-68**:
  ```python
  for key, value in data.items():
      if hasattr(flow, key):
          setattr(flow, key, value)
  ```
- This can accidentally set descriptors, hybrid properties, or SQLAlchemy internals if a caller passes unexpected keys. It also silently ignores unknown keys instead of failing fast.
- **Recommendation**: whitelist allowed columns explicitly or use a typed `FlowUpdate` schema.

#### MEDIUM — `get_pieces` has no result limit

- **Lines 88-115**: the query returns every row in `focus_builder_pieces_cache` when no search term is given. A large catalog could produce an unbounded response.
- **Recommendation**: add a default `limit` (e.g. 1000) and expose pagination if needed.

#### LOW — unnecessary `import builtins`

- **Line 7**: `import builtins`.
- **Line 90**: `builtins.list[dict[str, Any]]`.
- No local symbol shadows `list`. Use plain `list`.

#### LOW — unused `Optional` import

- **Line 1**: `from typing import Any, Optional` — `Optional` is not used.

---

### `src/core/api/v1/focus_builder/flows_router.py`

#### HIGH — `PUT /flows/{flow_id}` silently drops concurrent field updates

- **Lines 152-158**: see the `update_flow` service finding above. The router's branching logic is the immediate cause.
- **Recommendation**: always pass the full `FlowUpdate` payload to the service and let the service decide which fields to persist; do not split the update path in the router.

#### MEDIUM — inconsistent permission guards

- **Line 41**: `create_flow` requires `Permission.WRITE`.
- **Line 144**: `update_flow` has no `require_permission` dependency.
- **Line 205**: `delete_flow` has no `require_permission` dependency.
- Reads (`list_flows`, `get_flow`) legitimately do not need `WRITE`, but mutating updates and deletes should be guarded consistently with creates.
- **Recommendation**: add `require_permission(Permission.WRITE)` to `update_flow` and `delete_flow`.

#### LOW — `list_flows` catches generic `Exception` and swallows details

- **Lines 103-108**: returns a generic 500. This is acceptable, but the handler discards the original exception from the response. Ensure the exception is still logged at `error` level (it is, line 104).

---

### `src/core/api/v1/focus_builder/pieces_router.py`

#### MEDIUM — sync endpoint lacks admin guard despite docstring claim

- **Lines 74-94**: docstring says "Admin only", but there is no `require_permission(Permission.ADMIN)` or scope check.
- Any authenticated user can trigger a heavy external sync (rate-limited to 2/minute, but still unscoped).
- The feature spec review already flagged this as a follow-up; as code reviewer I confirm it is an open gap.
- **Recommendation**: add `require_permission(Permission.ADMIN)` or a dedicated `focus_builder:sync` scope.

#### LOW — file starts with a UTF-8 BOM

- **Line 1**: the file begins with byte sequence `EF BB BF` (verified with `file` and a hex dump). Python tolerates it, but it can break naive linters, diff tools, and code-generation scripts.
- **Recommendation**: save the file as UTF-8 without BOM.

---

### `src/alembic/versions/20260618_add_focus_builder_tables.py`

#### MEDIUM — migration creates `flows` but leaves `focus_builder_flows` unresolved

- **Lines 44-106**: creates `flows` with RLS. Good.
- **Lines 108-145**: creates `focus_builder_pieces_cache`. Good.
- The migration does **not** create `focus_builder_flows`, yet `FocusBuilderFlow` remains in `Base.metadata`. The mismatch is the root cause of the schema-drift findings above.
- **Recommendation**: either (a) add `focus_builder_flows` to the migration, or (b) remove `FocusBuilderFlow` from `model_registry.py` / `import_all_models.py`. Given the spec declares `flows` canonical, option (b) is preferred.

#### MEDIUM — RLS policy pattern differs from integration-test setup

- **Line 104**: uses `NULLIF(current_setting('app.current_tenant', true), '')::integer`.
- `tests/integration/conftest.py` uses `current_setting('app.current_tenant')::INTEGER` for other tables (no default, no `NULLIF`).
- The migration's pattern is safer (avoids errors when the setting is missing), but the divergence means integration tests do not exercise the exact production policy shape for `flows`.
- **Recommendation**: align the test RLS helper with the production `NULLIF` pattern.

---

### `tests/unit/domains/flows/test_service.py`

#### MEDIUM — does not cover `description` being ignored

- The tests verify lazy client instantiation and DB-first create, but they do not assert that `description` from `FlowCreate` is persisted.
- Given the service currently drops `description`, this is a real coverage gap.

#### MEDIUM — does not cover `update_flow` or `execute_flow`

- Only `create_flow` is tested. `update_flow` and `execute_flow` have error-handling and tenant-check paths that are not covered at unit level.

---

### `tests/unit/domains/flows/test_repository.py`

#### LOW — mocks SQLAlchemy behavior rather than asserting SQL

- Tests verify `flush()` is called and `commit()` is not, which is correct for the scope. They do not assert the actual SQL contains `tenant_id` filtering beyond a string-render check for `get`. This is acceptable for unit tests.

---

### `tests/integration/test_focus_builder_smoke.py`

#### LOW — only tests read endpoints

- Covers `GET /focus-builder/flows` and `GET /focus-builder/pieces`. Acceptable for a smoke test, but does not exercise `POST /flows`, `PUT /flows/{id}`, or `DELETE /flows/{id}`.

---

### `tests/integration/test_focus_builder_phase4.py`

#### HIGH — tests exercise a production-nonexistent table

- The file imports `FlowRepository` from `src.core.focus_builder.repositories` and `FocusBuilderFlow` from `src.core.focus_builder.models`, both of which target `focus_builder_flows`.
- The test fixture `postgres_session` relies on `Base.metadata.create_all`, which creates `focus_builder_flows` even though the SP-FB-001 migration does not.
- These 15 passing tests therefore give a false signal: they validate code and a table that do not exist in an Alembic-upgraded production database.
- **Recommendation**: either delete these legacy tests or rewrite them to use the canonical `src.domains.flows.repository.FlowRepository` and `flows` table.

---

## Cross-cutting concerns

### 1. Two parallel FocusBuilder implementations

The codebase currently has:

- Canonical path: `src.domains.flows.models.Flow` → `flows` table, used by routers.
- Legacy path: `src.core.focus_builder.models.FocusBuilderFlow` → `focus_builder_flows` table, used only by dead service/repository code and Phase 4 tests.

This duplication is the single largest source of risk in the change set. It causes schema drift, confusing test signals, and duplicated maintenance. The SP-FB-001 spec out-of-scopes full removal, but the current halfway state (model removed from model registry? No — still present) is unsafe.

### 2. RLS is not exercised in integration tests

`tests/integration/conftest.py` hard-codes `_ALLOWED_RLS_TABLES` and does not include `flows`. Production applies RLS via the migration, but no automated test verifies that a connection without `app.current_tenant` cannot read another tenant's flows. Tenant isolation is currently only verified at the SQL-render level in unit tests.

### 3. Pydantic v2 migration debt

`graph.dict()` and `flow_data.dict()` (in the legacy service) are Pydantic v1 methods. They work today but are deprecated. A project-wide Pydantic-v2 cleanup should replace these with `.model_dump()`.

### 4. Authorization inconsistency

`Permission.WRITE` is enforced for create but not update/delete in the flows router. `pieces/sync` claims admin-only behavior without enforcing it. These gaps contradict the RBAC-first design expected for tenant-scoped resources.

---

## Actionable recommendations (ordered by impact)

1. **Resolve the `focus_builder_flows` table drift** (HIGH)
   - Preferred: remove `FocusBuilderFlow` from `src/core/database/model_registry.py` and `src/core/database/import_all_models.py` (and delete `src/core/focus_builder/models.py`, `src/core/focus_builder/service.py`, and the `FlowRepository` half of `src/core/focus_builder/repositories.py` if no other code uses them).
   - Alternative: add a migration that creates `focus_builder_flows`. Not recommended because the spec already declares `flows` canonical.

2. **Fix the `PUT /flows/{id}` update split** (HIGH)
   - Modify `FocusBuilderService.update_flow` to accept the full `FlowUpdate` schema, compile the graph if present, and persist all supplied fields in a single repository call.

3. **Add RLS coverage for `flows` in integration tests** (HIGH)
   - Add `"flows"` to `_ALLOWED_RLS_TABLES` in `tests/integration/conftest.py` and add at least one integration test that proves cross-tenant reads are blocked at the DB level.

4. **Align authorization guards** (MEDIUM)
   - Add `require_permission(Permission.WRITE)` to `update_flow` and `delete_flow`.
   - Add an admin/scope guard to `POST /focus-builder/pieces/sync`.

5. **Clean up legacy repository code** (MEDIUM)
   - Remove or rewrite `src/core/focus_builder/repositories.py::FlowRepository` to use the canonical `Flow` model.
   - Fix `PiecesRepository` cache serialization to store and return complete objects.

6. **Modernize Pydantic calls** (MEDIUM)
   - Replace `graph.dict()` and `flow_data.dict()` with `.model_dump()`.

7. **Make `find_project_for_tenant` public** (MEDIUM)
   - Rename `_find_project_for_tenant` in `ActivePiecesClient` and update callers.

8. **Strengthen repository update safety** (MEDIUM)
   - Replace `hasattr`/`setattr` loops with explicit whitelists in both repositories.

9. **Small clean-ups** (LOW)
   - Remove `import builtins` and unused `Optional` imports.
   - Re-save `pieces_router.py` without UTF-8 BOM.
   - Pass `description` into `create_flow`.
   - Add a default limit to `get_pieces`.

---

## Approval gate

- **Critical issues**: 0 active production crashes, but the `focus_builder_flows` drift and the `PUT` update bug are production risks.
- **High issues**: 3 (schema drift, update split, missing RLS test coverage).
- **Verdict**: **REQUEST CHANGES**. The P0 fixes themselves are correct, but the legacy model drift and the router update bug must be resolved before this branch can be approved for merge.
