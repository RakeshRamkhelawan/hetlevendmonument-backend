# P5 Test Execution Guide
**SanskritiSetu AI Agent Platform - Integration, E2E, Performance & Regression Testing**

**Last Updated:** December 13, 2025
**Coverage Target:** 80% (up from 26% baseline)
**Test Phases:** P5.0 (Integration) → P5.1 (E2E) → P5.2 (Performance) → P5.3 (Regression)

---

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [Test Suite Overview](#test-suite-overview)
3. [P5.0: Integration Tests](#p50-integration-tests)
4. [P5.1: E2E Tests](#p51-e2e-tests)
5. [P5.2: Performance Tests](#p52-performance-tests)
6. [P5.3: Regression Tests](#p53-regression-tests)
7. [CI/CD Pipeline](#cicd-pipeline)
8. [Test Markers Reference](#test-markers-reference)
9. [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### Run All P5 Tests

```bash
# Run complete P5 test suite (Integration + E2E + Performance + Regression)
pytest tests/integration/ tests/e2e/ tests/performance/ tests/regression/ -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=html --cov-report=term-missing -v
```

### Run by Test Phase

```bash
# P5.0: Integration Tests
pytest tests/integration/test_p5_integration_comprehensive.py -v -m integration

# P5.1: E2E Tests
pytest tests/e2e/test_p5_e2e_user_journeys.py -v -m e2e

# P5.2: Performance Tests
pytest tests/performance/test_p5_performance_resilience.py -v -m performance

# P5.3: Regression Tests
pytest tests/regression/test_p5_critical_bug_fixes.py -v -m regression
```

### Run by Priority

```bash
# Smoke tests (fast, critical path)
pytest -v -m smoke

# Critical tests only
pytest -v -m critical

# Regression tests (prevent known bugs)
pytest -v -m regression
```

---

## 📊 Test Suite Overview

### Test Phase Summary

| Phase | Test Count | Focus | Duration | Coverage |
|-------|-----------|-------|----------|----------|
| **P5.0 Integration** | 7 tests | Cross-module flows | ~30s | CVA + Workflow + Tool Broker |
| **P5.1 E2E** | 3 tests | User journeys | ~45s | Complete platform flows |
| **P5.2 Performance** | 3 tests | Load & resilience | ~60s | 100 workflows, circuit breaker |
| **P5.3 Regression** | 5 tests | Known bug fixes | ~10s | Critical bug prevention |

### Test Pyramid

```
           ╱╲
          ╱  ╲  E2E Tests (3)
         ╱────╲  User Journeys
        ╱      ╲
       ╱  Integration Tests (7)  ╲
      ╱  Cross-Module Flows        ╲
     ╱────────────────────────────╲
    ╱                              ╲
   ╱  Unit Tests (2000+)            ╲
  ╱  Fast, Isolated, Comprehensive  ╲
 ╱──────────────────────────────────╲
```

---

## 🔗 P5.0: Integration Tests

**Purpose:** Validate realistic flows across multiple modules
**File:** `tests/integration/test_p5_integration_comprehensive.py`
**Duration:** ~30 seconds
**Coverage:** CVA Agent, Workflow Engine, Tool Broker, Domain Modules

### Test Scenarios

#### 1. CVA → Workflow → Domain Integration
**Test:** `test_cva_creates_and_executes_workflow`
**Flow:**
1. CVA agent transitions to PROACTIVE mode
2. Creates workflow spec (DAG with 3 tasks)
3. Workflow engine validates DAG
4. Executes tasks using fake providers
5. Updates domain models
6. CVA receives completion notification

**Command:**
```bash
pytest tests/integration/test_p5_integration_comprehensive.py::TestCVAWorkflowIntegration::test_cva_creates_and_executes_workflow -v
```

**Validates:**
- CVA state machine transitions
- Workflow DAG validation
- Task execution ordering (topological sort)
- Domain model persistence
- End-to-end integration

---

#### 2. Multi-Tenant Workflow Isolation
**Test:** `test_parallel_workflows_tenant_isolation`
**Flow:**
1. Creates 3 tenants with identical workflows
2. Executes workflows in parallel (asyncio.gather)
3. Verifies tenant data isolation
4. Checks no cross-tenant leakage

**Command:**
```bash
pytest tests/integration/test_p5_integration_comprehensive.py::TestMultiTenantWorkflowIsolation::test_parallel_workflows_tenant_isolation -v
```

**Validates:**
- Multi-tenant isolation
- Parallel execution correctness
- Database transaction isolation
- No race conditions

---

#### 3. Circuit Breaker State Transitions
**Test:** `test_circuit_breaker_opens_after_threshold_failures`
**Flow:**
1. Circuit breaker starts CLOSED
2. Simulates 3 consecutive failures
3. Circuit opens
4. Attempts call → Fails immediately (no retry overhead)
5. Waits for recovery timeout
6. Circuit transitions to HALF_OPEN
7. Successful call → Circuit closes

**Command:**
```bash
pytest tests/integration/test_p5_integration_comprehensive.py::TestCircuitBreakerRetryIntegration::test_circuit_breaker_opens_after_threshold_failures -v
```

**Validates:**
- Circuit breaker state machine (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Failure threshold enforcement
- Recovery timeout behavior
- Integration with retry logic

---

#### 4. Retry with Exponential Backoff
**Test:** `test_retry_with_exponential_backoff_integration`
**Flow:**
1. Function fails 2 times then succeeds
2. Retry with max_attempts=3, exponential backoff
3. Verifies backoff delays increase exponentially
4. Verifies final success

**Command:**
```bash
pytest tests/integration/test_p5_integration_comprehensive.py::TestCircuitBreakerRetryIntegration::test_retry_with_exponential_backoff_integration -v
```

**Validates:**
- Exponential backoff calculation
- Jitter randomization
- Retry success after transient failures

---

#### 5. Agent Coordination Flow
**Test:** `test_crisis_agent_orchestration_flow`
**Flow:**
1. Crisis event detected
2. Crisis orchestrator allocates specialist agents
3. Specialists execute in parallel
4. Results aggregated
5. Workflow updated with crisis response

**Command:**
```bash
pytest tests/integration/test_p5_integration_comprehensive.py::TestAgentCoordinationIntegration::test_crisis_agent_orchestration_flow -v
```

**Validates:**
- Agent pool allocation
- Multi-agent coordination
- Parallel execution
- Result aggregation

---

### Run All Integration Tests

```bash
# Run full integration suite
pytest tests/integration/test_p5_integration_comprehensive.py -v

# Run with detailed output
pytest tests/integration/test_p5_integration_comprehensive.py -v --tb=long

# Run with coverage
pytest tests/integration/test_p5_integration_comprehensive.py --cov=src.core.workflow --cov=src.core.agents --cov=src.core.tool_broker -v
```

---

## 🌐 P5.1: E2E Tests

**Purpose:** Validate complete user journeys from start to finish
**File:** `tests/e2e/test_p5_e2e_user_journeys.py`
**Duration:** ~45 seconds
**Coverage:** Complete platform flows (registration → execution → reporting)

### Test Scenarios

#### 1. Complete User Onboarding Journey (SMOKE TEST)
**Test:** `test_complete_user_onboarding_journey`
**Marker:** `@pytest.mark.smoke`
**Flow:**
1. User registers account
2. User logs in (JWT token)
3. User creates AI agent
4. User creates workflow
5. User executes workflow
6. User checks workflow status
7. User retrieves execution results

**Command:**
```bash
pytest tests/e2e/test_p5_e2e_user_journeys.py::test_complete_user_onboarding_journey -v
```

**This is the PRIMARY SMOKE TEST** - If this fails, the platform is broken.

---

#### 2. Crisis Management E2E
**Test:** `test_crisis_management_e2e_flow`
**Marker:** `@pytest.mark.critical`
**Flow:**
1. System detects critical security event (ransomware)
2. CVA transitions to CEO_MODE
3. Crisis orchestrator allocates specialists (cyber, PR, finance)
4. Specialists execute in parallel
5. Crisis workflow created and executed
6. Incident report generated

**Command:**
```bash
pytest tests/e2e/test_p5_e2e_user_journeys.py::test_crisis_management_e2e_flow -v
```

**Validates:**
- Crisis detection and classification
- CVA state machine (REACTIVE → CEO_MODE)
- Agent orchestration under pressure
- Complete crisis response pipeline

---

#### 3. Multi-Agent Collaboration Journey
**Test:** `test_multi_agent_collaboration_e2e`
**Flow:**
1. User submits research request
2. Knowledge agent retrieves documents
3. Data analysis agent processes findings
4. Reporting agent generates final report
5. CVA reviews and approves
6. Report stored and user notified

**Command:**
```bash
pytest tests/e2e/test_p5_e2e_user_journeys.py::test_multi_agent_collaboration_e2e -v
```

**Validates:**
- Multi-agent coordination
- Sequential task dependencies
- Data passing between agents
- Result aggregation

---

### Run All E2E Tests

```bash
# Run full E2E suite
pytest tests/e2e/ -v -m e2e

# Run smoke tests only
pytest tests/e2e/ -v -m smoke

# Run critical E2E tests
pytest tests/e2e/ -v -m "e2e and critical"
```

---

## ⚡ P5.2: Performance Tests

**Purpose:** Validate platform performance under load and resilience patterns
**File:** `tests/performance/test_p5_performance_resilience.py`
**Duration:** ~60 seconds
**NOT RUN ON EVERY COMMIT** - Runs on schedule or pre-release

### Test Scenarios

#### 1. Workflow Engine Load Test
**Test:** `test_workflow_engine_parallel_load`
**Load:**
- 10 tenants (enterprise tier)
- 10 workflows per tenant = 100 total
- 3 tasks per workflow (linear DAG)
- All executed in parallel

**Acceptance Criteria:**
- ✅ 100% success rate
- ✅ <60 seconds total execution time
- ✅ No database deadlocks
- ✅ Proper tenant isolation

**Command:**
```bash
pytest tests/performance/test_p5_performance_resilience.py::test_workflow_engine_parallel_load -v
```

**Performance Metrics:**
- Total execution time
- Average workflow duration
- Peak concurrent executions
- Database query count

---

#### 2. Circuit Breaker Behavior Under Load
**Test:** `test_circuit_breaker_state_transitions_under_load`
**Scenario:**
1. Circuit starts CLOSED
2. Simulate 50 rapid failures
3. Circuit opens
4. Verify fast rejection (<10ms)
5. Wait for recovery timeout
6. Circuit transitions to HALF_OPEN
7. Successful probe → Circuit closes
8. Repeat 3 times for stability

**Acceptance Criteria:**
- ✅ Circuit opens within 1 second
- ✅ Rejections when OPEN: <10ms
- ✅ Circuit recovers successfully
- ✅ Stable across 3 cycles

**Command:**
```bash
pytest tests/performance/test_p5_performance_resilience.py::test_circuit_breaker_state_transitions_under_load -v
```

---

#### 3. Database Connection Pool Stress
**Test:** `test_database_connection_pool_stress`
**Load:**
- 50 concurrent database operations
- Each operation: SELECT + INSERT + UPDATE + DELETE
- Total: 200 database operations

**Acceptance Criteria:**
- ✅ 100% success rate
- ✅ No connection timeouts
- ✅ Average latency <100ms
- ✅ No deadlocks

**Command:**
```bash
pytest tests/performance/test_p5_performance_resilience.py::test_database_connection_pool_stress -v
```

---

### Run All Performance Tests

```bash
# Run full performance suite
pytest tests/performance/ -v -m performance

# Run with timeout (5 minutes)
pytest tests/performance/ -v -m performance --timeout=300

# Run on main branch only (CI config)
# See .github/workflows/test-staged-pipeline.yml
```

---

## 🐛 P5.3: Regression Tests

**Purpose:** Prevent known critical bugs from recurring
**File:** `tests/regression/test_p5_critical_bug_fixes.py`
**Duration:** ~10 seconds
**RUN ON EVERY CI BUILD** (fast gate)

### Regression Test Policy

Every P0/P1 bug fix MUST have a regression test that:
1. Documents the original bug (issue #, severity, description)
2. Explains the root cause and the fix
3. Is marked `@pytest.mark.regression`
4. Critical bugs marked `@pytest.mark.critical`

### Test Scenarios

#### 1. Workflow DAG Cycle Detection Bug
**Issue:** #1234 (hypothetical)
**Severity:** CRITICAL
**Bug:** DAGValidator incorrectly reports cycle for valid diamond DAG
**Fix:** Updated DFS to use separate visited and rec_stack sets

**Command:**
```bash
pytest tests/regression/test_p5_critical_bug_fixes.py::test_regression_workflow_cycle_detection -v
```

---

#### 2. CVA State Machine Invalid Transition
**Issue:** #2345 (hypothetical)
**Severity:** CRITICAL
**Bug:** CVA allowed AUTONOMOUS → REACTIVE despite not in valid_transitions
**Fix:** Added validation in transition_to() to raise StateTransitionError

**Command:**
```bash
pytest tests/regression/test_p5_critical_bug_fixes.py::test_regression_cva_state_machine_transition_corruption -v
```

---

#### 3. Circuit Breaker Race Condition
**Issue:** #3456 (hypothetical)
**Severity:** HIGH
**Bug:** failure_count corrupted under concurrent failures
**Fix:** Added asyncio.Lock to protect state updates

**Command:**
```bash
pytest tests/regression/test_p5_critical_bug_fixes.py::test_regression_circuit_breaker_race_condition -v
```

---

#### 4. Multi-Tenant Data Leakage (SECURITY)
**Issue:** #4567 (hypothetical)
**Severity:** CRITICAL (SECURITY)
**Bug:** Workflow execution returned data from wrong tenant
**Fix:** Added tenant_id filter to all workflow queries

**Command:**
```bash
pytest tests/regression/test_p5_critical_bug_fixes.py::test_regression_multi_tenant_data_leakage -v
```

---

### Run All Regression Tests

```bash
# Run full regression suite
pytest tests/regression/ -v -m regression

# Run critical regressions only
pytest tests/regression/ -v -m "regression and critical"

# Run with fast-fail on first failure
pytest tests/regression/ -v -m regression --maxfail=1
```

---

## 🔄 CI/CD Pipeline

### Staged Test Pipeline

The CI pipeline runs tests in stages with fail-fast gates:

```
Stage 1: Unit Tests + Coverage (GATE)
    ↓ PASS (Coverage ≥ 80%)
Stage 2: Integration Tests (GATE)
    ↓ PASS
Stage 3: E2E Tests (GATE)
    ↓ PASS
Stage 4: Performance Tests (ADVISORY)
```

### Pipeline Configuration

**File:** `.github/workflows/test-staged-pipeline.yml`

**Triggers:**
- Push to `main` or `develop`
- Pull request to `main` or `develop`
- Scheduled daily at 2 AM UTC

**Stage Details:**

| Stage | Runs | Timeout | Failure Action |
|-------|------|---------|----------------|
| 1. Unit + Regression | Always | 15 min | Block PR merge |
| 2. Integration | If Stage 1 passes | 20 min | Block PR merge |
| 3. E2E | If Stage 2 passes | 30 min | Block PR merge |
| 4. Performance | Only on main/schedule | 45 min | Advisory (don't block) |

---

## 🏷️ Test Markers Reference

### Available Markers

```python
@pytest.mark.unit           # Unit tests (fast, isolated)
@pytest.mark.integration    # Integration tests (cross-module)
@pytest.mark.e2e            # End-to-end user journeys
@pytest.mark.performance    # Performance and load tests
@pytest.mark.regression     # Regression tests for known bugs
@pytest.mark.critical       # Critical path tests (run on every build)
@pytest.mark.smoke          # Smoke tests for basic functionality
@pytest.mark.slow           # Slow running tests (>30s)
@pytest.mark.asyncio        # Async tests (auto-applied)
```

### Marker Combinations

```bash
# Run critical unit tests
pytest -v -m "unit and critical"

# Run integration tests but skip slow ones
pytest -v -m "integration and not slow"

# Run smoke tests + critical regressions
pytest -v -m "smoke or (regression and critical)"

# Run E2E excluding performance
pytest -v -m "e2e and not performance"
```

---

## 🔧 Troubleshooting

### Common Issues

#### 1. Tests Fail with "Coverage below threshold"

**Problem:** Unit tests pass but coverage gate fails

**Solution:**
```bash
# Check current coverage
pytest tests/unit/ --cov=src --cov-report=term-missing

# Find uncovered lines
pytest tests/unit/ --cov=src --cov-report=html
# Open htmlcov/index.html in browser

# Adjust threshold in .github/workflows/test-staged-pipeline.yml
# COVERAGE_THRESHOLD: 80  # Adjust if needed
```

---

#### 2. Integration Tests Hang or Timeout

**Problem:** Integration tests timeout after 60 seconds

**Solution:**
```bash
# Run with increased timeout
pytest tests/integration/ --timeout=120

# Debug specific test
pytest tests/integration/test_p5_integration_comprehensive.py::test_name -v --tb=long

# Check for database deadlocks
# Review logs for "database is locked" errors
```

---

#### 3. E2E Tests Fail Due to Missing Fixtures

**Problem:** `fixture 'test_tenant' not found`

**Solution:**
```bash
# Verify conftest.py is loading
pytest --fixtures | grep test_tenant

# Check PYTHONPATH
export PYTHONPATH=src
pytest tests/e2e/ -v

# Run from project root
cd /path/to/SanskritiSetu.org
pytest tests/e2e/ -v
```

---

#### 4. Performance Tests Advisory Failures

**Problem:** Performance tests fail but don't block PR

**Solution:**
Performance tests are **advisory** - they don't block PR merges.
They run only on `main` branch or scheduled builds.

To investigate:
```bash
# Run locally
pytest tests/performance/ -v -m performance

# Check GitHub Actions artifacts
# Navigate to Actions → Test Pipeline → Stage 4 Artifacts
```

---

## 📈 Coverage Tracking

### Current Coverage Status

**Baseline (P4.0):** 11.73%
**Target (P5.0):** 80%
**Current:** Check [latest CI run](https://github.com/RakeshRamkhelawan/SanskritiSetu.org/actions)

### Generate Coverage Report

```bash
# HTML report (interactive)
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html

# Terminal report (quick check)
pytest tests/ --cov=src --cov-report=term-missing

# XML report (for CI)
pytest tests/ --cov=src --cov-report=xml
```

---

## 🎯 Next Steps

After completing P5:

1. **Monitor CI Pipeline:** Track test stability and coverage trends
2. **Add Regression Tests:** For each new bug fix, add regression test
3. **Performance Baselines:** Establish performance benchmarks
4. **Flakiness Detection:** Monitor and fix flaky tests
5. **Documentation:** Keep this guide updated with new scenarios

---

## 📚 Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio Guide](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov Usage](https://pytest-cov.readthedocs.io/)
- [GitHub Actions Workflows](https://docs.github.com/en/actions)

---

**Last Updated:** December 13, 2025
**Maintained By:** Test Engineering Team
**Questions?** Open an issue or contact the team.
