# Subagent Quality Review: SP-FB-001 FocusBuilder P0-fixes

**Scope:** src/domains/flows/*, src/core/focus_builder/*, src/core/database/model_registry.py, src/core/api/v1/focus_builder/flows_router.py, src/core/api/v1/focus_builder/pieces_router.py, src/alembic/versions/20260618_add_focus_builder_tables.py, tests/unit/domains/flows/*, tests/integration/test_focus_builder_smoke.py, tests/integration/test_focus_builder_phase4.py

**Environment:** Python 3.13.7, pytest-8.3.4, Windows 11, project venv.

**Reviewer:** independent quality subagent (no prior context assumed).

---

## Summary verdict: PASS WITH WARNINGS

The change set is functionally sound and the test suite reports green, but it does not pass all quality gates cleanly.
Blockers for a clean PASS:

1. `ruff format --check` fails on 5 files.
2. `mypy --strict` reports 50 in-scope errors in the new test files (plus 2 pre-existing governance errors reached through imports).
3. Multiple OWASP Broken Access Control gaps in the new routers.
4. A UTF-8 BOM at the start of `pieces_router.py`.
5. A migration / model mismatch: `FocusBuilderFlow` targets `focus_builder_flows`, but the SP-FB-001 migration only creates `flows`.

None of the security findings are exploitable against a tenant boundary (tenant isolation is enforced at the DB layer), but the RBAC inconsistency and dead-code mismatch must be resolved before this can be considered production-hardened.

---

## Tool outputs

### 1. ruff check

```text
All checks passed!
```

### 2. ruff format --check

```text
Would reformat: src\alembic\versions\20260618_add_focus_builder_tables.py
Would reformat: src\core\api\v1\focus_builder\pieces_router.py
Would reformat: src\core\focus_builder\models.py
Would reformat: src\domains\flows\repository.py
Would reformat: tests\unit\domains\flows\test_service.py
5 files would be reformatted, 8 files already formatted
```

### 3. pyright

```text
Config contains unrecognized setting "baselineFile".
0 errors, 0 warnings, 0 informations
WARNING: there is a new pyright version available (v1.1.408 -> v1.1.410).
```

Type-checking passes for all changed files.

### 4. mypy (timeout 120 s, did not time out)

```text
Found 52 errors in 5 files (checked 13 source files)
```

Breakdown:

- 2 errors are pre-existing in `src/core/governance/models.py` (`Base` not valid as a type), reached because the routers import `src.core.auth.auth_service`. These are outside the declared scope.
- 50 errors are in-scope:
  - `tests/integration/test_focus_builder_phase4.py`: 20 `no-untyped-def` errors (fixtures and test methods lack annotations).
  - `tests/unit/domains/flows/test_repository.py`: 14 errors (`method-assign` on mocked `AsyncSession`, missing annotations on nested mock functions, and `attr-defined` on `assert_not_called`).
  - `tests/unit/domains/flows/test_service.py`: 4 errors (`method-assign`, missing `dict` type parameters, incompatible list item for `ReactFlowNode`).
  - `src/core/governance/models.py` (reached transitively): 2 pre-existing errors as noted above.

`mypy` finished within the timeout; no timeout occurred.

### 5. Hardcoded secrets scan

No hardcoded passwords, API keys, tokens, private keys, or cloud credentials were found in any of the changed files.

### 6. Non-ASCII / emoji scan

One non-ASCII character found:

- `src/core/api/v1/focus_builder/pieces_router.py:1` column 0: U+FEFF (UTF-8 BOM) at the very start of the file, before the docstring.

No emoji were found in changed code, comments, or log strings.

---

## Security scan findings (OWASP Top 10 quick scan)

### Broken Access Control -- HIGH

The new Focus Builder endpoints do not consistently enforce RBAC permissions.

- `src/core/api/v1/focus_builder/flows_router.py:83-108` `list_flows`: only requires `get_current_user_dependency`; no `require_permission` check.
- `src/core/api/v1/focus_builder/flows_router.py:111-133` `get_flow`: only requires `get_current_user_dependency`; no `require_permission` check.
- `src/core/api/v1/focus_builder/flows_router.py:136-195` `update_flow`: only requires `get_current_user_dependency`; no `require_permission` check.
- `src/core/api/v1/focus_builder/flows_router.py:198-228` `delete_flow`: only requires `get_current_user_dependency`; no `require_permission` check.
- `src/core/api/v1/focus_builder/pieces_router.py:28-46` `list_pieces`: no permission check.
- `src/core/api/v1/focus_builder/pieces_router.py:49-71` `get_piece_schema`: no permission check.
- `src/core/api/v1/focus_builder/pieces_router.py:74-94` `sync_pieces`: docstring says "Admin only", but no admin or permission check is performed; any authenticated user can trigger a sync.

Tenant isolation is still enforced by the repository layer (`tenant_id` filters and RLS), so cross-tenant access is blocked. Within a tenant, however, any authenticated user can create, read, update, delete, and trigger syncs. Only `create_flow` enforces `Permission.WRITE`.

### Insecure Design / Security Misconfiguration -- HIGH

Two competing flow models exist:

- `src/domains/flows/models.py:16` `Flow` maps to table `flows`.
- `src/core/focus_builder/models.py:11` `FocusBuilderFlow` maps to table `focus_builder_flows`.

The SP-FB-001 migration (`src/alembic/versions/20260618_add_focus_builder_tables.py`) creates only:

- `flows`
- `focus_builder_pieces_cache`

It does **not** create `focus_builder_flows`. In integration tests, `Base.metadata.create_all()` silently creates the table because `FocusBuilderFlow` is registered in `model_registry.py`. In production, an Alembic-upgraded database will be missing `focus_builder_flows`, so any code path using `src/core.focus_builder.repositories.FlowRepository` or `FocusBuilderFlow` will fail at runtime.

Currently the routers use `src.domains.flows.service.FocusBuilderService` (which uses `Flow` / `flows`), but `tests/integration/test_focus_builder_phase4.py` exercises `src.core.focus_builder.repositories.FlowRepository` (which uses `FocusBuilderFlow` / `focus_builder_flows`). This leaves dead, unmigrated code in the production path.

### Injection -- LOW / INFORMATIONAL

All SQL is built with SQLAlchemy 2.0 parameterized statements. User-supplied `search` terms are interpolated into `ilike()` patterns (`f"%{search}%"`), but SQLAlchemy binds them as parameters; no SQL injection vector was identified. Wildcard characters (`%`, `_`) are passed through, which is normal search behavior.

### Vulnerable and Outdated Components -- NONE

No new dependencies or version pins were introduced in the changed files.

### Security Logging and Monitoring Failures -- NONE

All endpoints include structured logging (`loguru`) and OpenTelemetry span enrichment via `enrich_span`. No sensitive values are logged.

### Identification and Authentication Failures -- NONE

All endpoints depend on `get_current_user_dependency` and require a valid bearer token for tenant resolution.

---

## Formatting / type-check findings

### Formatting failures (ruff format --check)

Files that need `ruff format`:

1. `src/alembic/versions/20260618_add_focus_builder_tables.py`
2. `src/core/api/v1/focus_builder/pieces_router.py`
3. `src/core/focus_builder/models.py`
4. `src/domains/flows/repository.py`
5. `tests/unit/domains/flows/test_service.py`

Notable formatting issues observed (before running formatter):

- `src/core/api/v1/focus_builder/pieces_router.py:1` starts with a UTF-8 BOM; this is also a non-ASCII violation.
- `src/domains/flows/repository.py:7` uses `import builtins` and `builtins.list[...]` instead of plain `list[...]`; ruff wants it reformatted/normalized.
- `src/core/focus_builder/repositories.py:11` has the same `import builtins` pattern and also defines `OptimisticLockError` at the bottom of the module (line 385) after it is raised (line 135). This works at runtime but is poor ordering; ruff does not flag it, but it is a maintainability issue.

### Type-check failures (mypy)

The new test files are not `mypy --strict` clean. Key patterns:

- Assigning to methods of `AsyncMock` instances (`mock_db.commit = AsyncMock()`), which `mypy` flags as `method-assign`.
- Nested async helper functions without return type annotations.
- Fixtures in `test_focus_builder_phase4.py` without return types.
- `ReactFlowGraph(nodes=[{...}])` passes a raw dict where `list[ReactFlowNode]` is expected; Pydantic accepts it at runtime, but mypy reports `list-item`.

Production code in scope type-checks cleanly with pyright. The mypy errors are almost entirely in tests and are mostly stylistic under `strict=true`, but they do fail the configured gate.

### Other code-quality observations

- Unused imports:
  - `src/domains/flows/service.py:3` imports `Optional` but never uses it.
  - `src/domains/flows/repository.py:1` imports `Optional` but never uses it.
  - `src/domains/flows/models.py:2` imports `Optional` but never uses it.
  - `src/core/focus_builder/models.py:2` imports `Optional` but never uses it.
  - `src/core/focus_builder/repositories.py:1` imports `Optional` but never uses it.
- `src/core/focus_builder/repositories.py:190-239` `batch_delete` and `batch_update_status` accept a `tenant_id` argument while the repository already stores `_tenant_id`. Using the argument overrides the repository's own isolation context and is error-prone; callers could pass the wrong tenant ID. The methods should use `self._tenant_id` consistently.
- `src/core/focus_builder/repositories.py:169-188` `batch_create` does not inject `tenant_id`; it relies on the caller-provided data dict. If omitted, the DB `NOT NULL` constraint will raise. The domain `FlowRepository.create` injects `tenant_id` correctly (`src/domains/flows/repository.py:51`).
- `src/domains/flows/service.py:247` calls the private method `self.ap_client._find_project_for_tenant(self.tenant_id)`. Calling a private method across module boundaries is a maintainability/code-coupling issue.

---

## Actionable recommendations

### Must fix before merge (blockers)

1. **Run `ruff format` on the 5 failing files** and re-verify with `ruff format --check`.
2. **Remove the UTF-8 BOM** from `src/core/api/v1/focus_builder/pieces_router.py:1`.
3. **Resolve the `flows` vs `focus_builder_flows` split**:
   - Option A: Drop `src/core/focus_builder/models.py` and `src/core/focus_builder/repositories.py` if they are not used by production routers, and migrate Phase 4 tests to use `src.domains.flows.repository.FlowRepository` and `src.domains.flows.models.Flow`.
   - Option B: If the core models are intended to be canonical, add a migration step that creates `focus_builder_flows` with the same RLS policy, and reconcile the duplicate models so only one flow abstraction exists.
4. **Add RBAC permission checks** to `list_flows`, `get_flow`, `update_flow`, `delete_flow`, and `sync_pieces` to match the `Permission.WRITE` check already used in `create_flow`. `sync_pieces` should enforce an admin permission, not just a docstring claim.
5. **Clean up mypy strict errors in the new test files**:
   - Add return type annotations to fixtures and test methods.
   - Use `cast(AsyncMock, mock_db.commit)` or a `Mock`/`MagicMock` typed wrapper instead of direct method assignment.
   - Construct `ReactFlowNode(...)` explicitly instead of passing a dict to `ReactFlowGraph(nodes=[...])`.

### Should fix (non-blocking but recommended)

6. Remove unused `Optional` imports in the five files noted above.
7. Replace `import builtins` and `builtins.list[...]` with plain `list[...]` in `src/domains/flows/repository.py` and `src/core/focus_builder/repositories.py`.
8. In `src/core/focus_builder/repositories.py`:
   - Move `OptimisticLockError` to the top of the file (before it is raised).
   - Make `batch_delete` and `batch_update_status` use `self._tenant_id` and remove the `tenant_id` parameter, or assert that the passed value equals `self._tenant_id`.
   - Inject `tenant_id` in `batch_create` the same way `src.domains.flows.repository.FlowRepository.create` does.
9. In `src/domains/flows/service.py:247`, use a public API on `ActivePiecesClient` to resolve the tenant project ID, or document why a private method must be used.
10. Add a CI step that runs `ruff format --check` and `mypy` on the changed files so regressions are caught automatically.

---

## Final assessment

| Gate | Result | Notes |
| --- | --- | --- |
| ruff check | PASS | 0 errors |
| ruff format --check | FAIL | 5 files need formatting |
| pyright | PASS | 0 errors, 0 warnings |
| mypy | FAIL | 50 in-scope errors in tests; finished within timeout |
| Secrets scan | PASS | No findings |
| OWASP quick scan | WARNINGS | Broken access control, migration/model mismatch |
| Non-ASCII / emoji | FAIL | UTF-8 BOM in pieces_router.py |

**Overall: PASS WITH WARNINGS.**
The functional implementation and tests are solid, but the formatting, type-check, access-control, and migration consistency gaps must be addressed before this change can be considered fully production-ready.
