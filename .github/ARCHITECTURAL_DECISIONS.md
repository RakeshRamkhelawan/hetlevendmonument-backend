# Technical Decisions & Architecture

**Project**: SanskritiSetu Test Infrastructure Phase 3
**Last Updated**: 2025-12-08
**Decision Owner**: AI Infrastructure Team

---

## Core Architecture Decisions

### 0. AI Act Governance (ADR-031)

**Decision**: Mandatory platform-wide governance contract for all AI entrypoints

**Rationale**:
- EU AI Act Art. 12/13/50/26(6) compliance by 2 August 2026
- One enforceable governance standard across all AI surfaces (Copilot, CVA, Focus Builder, ALS, Agentic)
- Canonical pipeline: Identity → Proposal → Policy → Council/Gatekeeper → Audit → Execute → Transparency
- Autonomy ladder L1-L4 controls deployment risk

**Status**: ✅ Implemented (6 sprints, 30 evidence records, 40/40 matrix routes closed, 2026-05-26)

**Post-audit gap fixes (2026-05-26)**:
- 6 critical code gaps resolved after EU AI Act audit
- `require_council_approval()` reusable helper standardises Council gate across all routes
- CVA /chat, Focus Builder /ai/suggest+generate, ALS /tasks+/broadcast, Agentic /generate all enforce Council deliberation
- Agentic WS tenant_id payload fallback removed (security fix)
- 20 new regression tests added, 0 regressions detected

**Evidence**:
- `docs/adr/031-platform-wide-ai-act-governance-and-wiring.md`
- `docs/Aiact 2026/evidence/EVIDENCE_INDEX.md`
- `docs/audits/ai-route-compliance-matrix-2026-05-26.md`
- `docs/audits/EU_AI_ACT_AUDIT_2026-05-26.md`

### 1. Test Framework Strategy

**Decision**: Monolithic pytest suite + production-mirror stack approach

**Rationale**:
- Single pytest config (`pytest.ini` + `pytest_reboot.ini`) for consistency
- Production-mirror stack (`docker-compose.test.prod.yml`) for realistic E2E testing
- Fixture isolation via `TenantFilterBypass` context manager
- Forward-only data pattern (UUIDs + timestamps) avoids DB resets

**Impact**:
- ✅ Reduced fixture conflicts from 12 errors → 0 errors
- ✅ 98.5% test pass rate maintained
- ✅ Realistic integration testing without full production deployment

**Alternative Considered**: Separate integration vs unit test suites
- Rejected: Duplicated fixtures, inconsistent test data patterns

---

### 2. External State Management (Amnesiac Coder Pattern)

**Decision**: Use `.ai/project_state.json` as Single Source of Truth for task state

**Rationale**:
- Copilot context window limits (~6000 tokens) make long-term memory unreliable
- JSON file persists across chat sessions
- Enables "context reset" workflow: new chat after each task completion
- Reduces hallucination: "passes": false is binary proof of incompleteness

**Files**:
- `.ai/project_state.json` - Task state (MANDATORY)
- `.ai/decisions.md` - Architecture decisions (for reference)
- `.ai/COPILOT_INSTRUCTIONS.md` - Copilot behavior guidelines

**Impact**:
- 100% task tracking accuracy
- Zero context contamination between sessions
- Reproducible AI-assisted development

---

### 3. Test Priority Matrix (P0-P3)

**Decision**: Four-tier priority system based on release blockers

| Priority | Tests | Release Blocker? | Estimated Time |
|----------|-------|------------------|-----------------|
| P0 | 22 tasks (Validation, Infra, Scaffolding, E2E, Orch) | YES | 8-10 days |
| P1 | 13 tasks (Env, Scripts, E2E+, Observability) | YES | 4.5 days |
| P2 | 14 tasks (Chaos, Load, CI/CD) | NO | 6 days |
| P3 | 4 tasks (Documentation) | NO | 1 day |

**Rationale**:
- P0 must pass before beta release
- P1 must pass before production release
- P2/P3 can be deferred post-launch if needed

---

### 4. Test Data Pattern: Forward-Only

**Decision**: No database resets between tests. Generate unique data per test.

**Rationale**:
- UUID + timestamp combinations ensure uniqueness
- No circular dependencies on cleanup
- Faster test execution (no truncate operations)
- Simpler fixtures with fewer state transitions

**Pattern**:
```python
@pytest.fixture
def unique_tenant():
    tenant_id = uuid4()
    timestamp = datetime.utcnow().isoformat()
    return f"tenant_{tenant_id}_{timestamp}"
```

---

### 5. Docker Compose Split Strategy

**Files Used**:
- `docker-compose.base.yml` - Shared services (PostgreSQL, Redis)
- `docker-compose.dev.yml` - Local development (hot-reload)
- `docker-compose.test.yml` - Unit/integration tests (optimized)
- `docker-compose.test.prod.yml` - Production-mirror (full realistic stack)
- `docker-compose.prod.yml` - Actual production

**Rationale**:
- Base = DRY principle, no duplication
- Test.yml = Lightweight for fast CI/CD
- Test.prod.yml = Realistic E2E environment (includes Mailhog, RabbitMQ, full setup)

**Impact**:
- Tests run in ~10 minutes vs 30+ minutes with prod config
- CI/CD efficiency without sacrificing E2E realism

---

### 6. Fixture Scoping Strategy

**Decision**: Function-scoped fixtures with session-scoped async engine

```python
# session-scoped (reused across tests)
@pytest.fixture(scope="session")
async def async_engine():
    ...

# function-scoped (fresh per test)
@pytest.fixture
async def db_session(async_engine):
    async with AsyncSession(async_engine) as session:
        yield session
        await session.rollback()  # Clean up
```

**Rationale**:
- Session engine: Amortizes connection overhead
- Function session: Prevents cross-test pollution
- Explicit rollback: No shared transaction state

**Related Fix**: Added `TenantFilterBypass` context to wrap fixture queries, preventing tenant auto-filter blocking setup

---

### 7. CI/CD Quality Gate Strategy

**Decision**: GitHub Actions pipeline with mandatory gates (reference: `.github/copilot-instructions.md`)

**Gates in Order**:
1. Task sequencing check (P0 before P1-4)
2. Bandit security scan (no HIGH/CRITICAL)
4. Safety dependency audit (no CVEs)
5. Mypy strict type checking
6. Black + isort formatting
7. Pylint 9.0+ score
8. pytest > 80% coverage
9. Task-specific verifications (grep, imports)

**Rationale**:
- Gates are ordered: fail-fast on policy, then on quality, then on functionality
- Mandatory: None can be overridden manually (except in emergency)
- Auto-remediation where possible (Black formatting, isort imports)

---

### 8. Operational Runbook Consolidation

**Decision**: Single source of truth for operational guidance: `docs/OPERATIONAL_RUNBOOK_TESTSUITE.md`

**Contents**:
- Part 1: Setup (venv, dependencies, .env)
- Part 2-5: Test execution (unit, integration, prod-mirror, chaos/load)
- Part 6: CI/CD simulation locally
- Part 7: Troubleshooting & debugging commands
- Part 8: Test structure documentation
- Appendix: Quick cheat sheet

**Impact**:
- New team members onboard in < 30 minutes
- Reproducible local development workflow
- Standard troubleshooting playbook

---

### 9. Deprecated Files Deprecation Policy

**Decision**: Keep old docs marked [DEPRECATED] for 30 days, then archive

| File | Status | Reason |
|------|--------|--------|
| `docs/TEST_INFRASTRUCTURE_TODO.md` | [DEPRECATED] | Merged into KANBAN_BOARD_VIBECODING.md + project_state.json |
| `.github/copilot-instructions.md` | Active | CI/CD automation guardrails |
| `KANBAN_BOARD_VIBECODING.md` | Active | Primary task board (human-readable) |
| `.ai/project_state.json` | Active | Copilot working file (machine-readable) |

---

## Technology Stack Decisions

### Test Framework: pytest + pytest-asyncio

**Why pytest**:
- Parametrization: `@pytest.mark.parametrize` reduces test duplication
- Async support: `pytest-asyncio` for async/await patterns
- Fixture system: Powerful but requires care (see fixture scoping above)

**Alternatives Rejected**:
- unittest: Too verbose, no parametrization
- nose: Deprecated
- Trial (Twisted): Not needed, we use asyncio not Twisted

### Async Runtime: asyncio (not Twisted)

**Why asyncio**:
- Built into Python 3.10+
- SQLAlchemy AsyncSession uses asyncio natively
- FastAPI uses asyncio

**Config**:
```ini
[tool:pytest]
asyncio_mode = auto
```

### Coverage: pytest-cov

**Why pytest-cov**:
- Local development feedback (instant)
- CI/CD gate via coverage reports

**Threshold**: 80% minimum (can raise to 85%+ after P0 complete)

---

## Known Limitations & Workarounds

### 1. Test Pollution from Tenant Auto-Filtering

**Problem**: Session-scoped fixture initializing tenant auto-filtering blocks other fixture queries

**Solution**: `TenantFilterBypass()` context manager in tests/conftest.py
```python
@pytest.fixture
def test_tenant():
    with TenantFilterBypass():
        # Query unfiltered
        tenant = create_tenant()
    return tenant
```

**Status**: ✅ Fixed (0 errors, Dec 5, 2025)

### 2. Pytest-xdist Process Isolation

**Problem**: Running tests in parallel can reveal race conditions hidden in sequential runs

**Solution**: Installed `pytest-xdist`, use `-n auto` for parallel runs
```bash
pytest tests/unit/ -n auto  # Run in N worker processes
```

**Status**: ✅ Integrated (Dec 4, 2025)

---

## Performance Benchmarks (as of Dec 8, 2025)

| Test Category | Duration | Count | Status |
|---------------|----------|-------|--------|
| Unit tests (all) | ~2 min | 2625 | ✅ 98.5% pass |
| Integration tests | ~5 min | 170 | ✅ 100% pass |
| Production-mirror E2E | ~10 min | TBD | ⏳ TODO (P0.F) |
| Full suite + coverage | ~15 min | 2795 | ✅ Achievable |

**Goal**: Keep full test run under 15 minutes for CI/CD feedback loop

---

## Next Review Point

- **Trigger**: When P0 (22 tasks) complete
- **Review**: Coverage results, performance, fixture stability
- **Action**: Adjust P1/P2 priorities based on learnings
