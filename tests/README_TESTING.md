# Phase 3 Complete Test Suite
## Sprints 1-5 Integration & E2E Tests

This directory contains comprehensive integration and end-to-end tests covering all Phase 3 sprints.

---

## 📁 Test Structure

```
tests/
├── integration/
│   ├── test_sprint1_onboarding_auth.py      # Sprint 1: Auth, RBAC, Multi-tenant
│   ├── test_sprint2_specialist_agents.py    # Sprint 2: Agent registration & routing
│   ├── test_sprint3_workflows.py            # Sprint 3: Workflow execution
│   ├── test_sprint4_rag_tools.py            # Sprint 4: RAG retrieval & Tool broker
│   └── test_sprint5_hardening.py            # Sprint 5: Resilience & feature flags
└── e2e/
    └── test_complete_phase3_journey.py      # Complete user journey (all sprints)
```

---

## 🎯 Test Coverage

### Sprint 1: Onboarding & Authentication (5 tests)
- ✅ Complete tenant onboarding flow
- ✅ RBAC permissions enforcement
- ✅ JWT token lifecycle
- ✅ Multi-tenant data isolation
- ✅ Password security workflow

### Sprint 2: Specialist Agents (6 tests)
- ✅ Agent registration and discovery
- ✅ Category-based routing
- ✅ Agent execution with context
- ✅ Multi-agent collaboration
- ✅ Agent state persistence
- ✅ Capability matching

### Sprint 3: Workflows & Procedures (6 tests)
- ✅ Complete workflow lifecycle
- ✅ Multi-step procedure execution
- ✅ Error handling and rollback
- ✅ Conditional branching (if-then-else)
- ✅ Parallel step execution
- ✅ Workflow scheduling (cron)

### Sprint 4: RAG & Tool Integration (7 tests)
- ✅ Document ingestion and chunking
- ✅ Vector search retrieval
- ✅ Tool registration and discovery
- ✅ Tool execution via broker
- ✅ RAG-enhanced agent queries
- ✅ Circuit breaker pattern
- ✅ Chunking strategies

### Sprint 5: Hardening & Production (7 tests)
- ✅ Feature flag rollout/rollback
- ✅ Circuit breaker resilience
- ✅ Graceful degradation
- ✅ Concurrent load handling
- ✅ Disaster recovery integrity
- ✅ Performance under sustained load
- ✅ Tenant isolation under load

### E2E: Complete Journey (2 tests)
- ✅ Full customer journey (all 5 sprints)
- ✅ Multi-tenant concurrent operations

**Total: 38 comprehensive tests**

---

## 🚀 Quick Start

### Prerequisites

```powershell
# Ensure test environment is configured
$env:TESTING = "1"
$env:DATABASE_URL = "sqlite+aiosqlite:///file:memdb1?mode=memory&cache=shared&uri=true"

# Install test dependencies
pip install -r requirements-test.txt
```

### Run All Tests

```powershell
# Run all integration tests
pytest tests/integration/ -v

# Run all E2E tests
pytest tests/e2e/ -v --tb=short

# Run everything
pytest tests/integration/ tests/e2e/ -v
```

### Run by Sprint

```powershell
# Sprint 1 only
pytest tests/integration/test_sprint1_onboarding_auth.py -v

# Sprint 2 only
pytest tests/integration/test_sprint2_specialist_agents.py -v

# Sprint 3 only
pytest tests/integration/test_sprint3_workflows.py -v

# Sprint 4 only
pytest tests/integration/test_sprint4_rag_tools.py -v

# Sprint 5 only
pytest tests/integration/test_sprint5_hardening.py -v
```

### Run with Coverage

```powershell
# Generate coverage report
pytest tests/integration/ tests/e2e/ --cov=src --cov-report=html --cov-report=term-missing

# View HTML report
start htmlcov/index.html
```

### Run Specific Test

```powershell
# Run single test
pytest tests/integration/test_sprint1_onboarding_auth.py::test_complete_tenant_onboarding_flow -v

# Run test pattern
pytest -k "rbac" -v

# Run with specific markers
pytest -m e2e -v
```

---

## 🔍 Test Configuration

### pytest.ini Settings

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
markers =
    e2e: End-to-end tests (select with '-m e2e')
    integration: Integration tests
    slow: Slow-running tests
```

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TESTING` | Enable test mode | `1` |
| `DATABASE_URL` | Test database URL | `sqlite+aiosqlite:///...` |
| `JWT_SECRET` | JWT secret for tests | `test-secret-key` |
| `REDIS_URL` | Redis URL (optional) | `redis://localhost:6380/1` |

---

## 📊 Expected Results

### Success Criteria

- **All tests pass**: 38/38
- **Coverage**: ≥95%
- **No data leakage**: Tenant isolation verified
- **No race conditions**: Concurrent operations succeed
- **Rollback safety**: Feature flags work correctly

### Performance Targets

| Test Category | Target | Acceptable |
|---------------|--------|------------|
| Unit tests | <10s | <30s |
| Integration tests | <60s | <120s |
| E2E tests | <120s | <240s |
| Complete suite | <180s | <300s |

---

## 🛠️ Troubleshooting

### Common Issues

#### 1. Database Connection Errors

```powershell
# Ensure test mode is enabled
$env:TESTING = "1"

# Use in-memory SQLite for tests
$env:DATABASE_URL = "sqlite+aiosqlite:///file:memdb1?mode=memory&cache=shared&uri=true"
```

#### 2. Import Errors

```powershell
# Set PYTHONPATH
$env:PYTHONPATH = "src"

# Or run from project root
cd c:\Users\rsram\OneDrive\Documenten\GitHub\SanskritiSetu.org
pytest tests/
```

#### 3. Async Errors

```ini
# In pytest.ini
asyncio_mode = auto
```

#### 4. Test Isolation Issues

```python
# Each test should use fresh fixtures
# Ensure conftest.py has proper cleanup
```

---

## 📝 Writing New Tests

### Template

```python
@pytest.mark.asyncio
async def test_feature_name(async_client: AsyncClient):
    """
    Test description.

    Flow:
    1. Setup step
    2. Action step
    3. Verification step
    """
    # Arrange
    tenant_payload = {...}

    # Act
    response = await async_client.post("/api/v1/resource/", json=tenant_payload)

    # Assert
    assert response.status_code == 201
```

### Best Practices

1. **Descriptive Names**: `test_feature_scenario_expected_result`
2. **AAA Pattern**: Arrange → Act → Assert
3. **Isolation**: Each test is independent
4. **Cleanup**: Use fixtures for automatic cleanup
5. **Documentation**: Clear docstrings with flow description

---

## 🎯 CI/CD Integration

### GitHub Actions

```yaml
- name: Run Integration Tests
  run: pytest tests/integration/ -v --cov=src --cov-fail-under=95

- name: Run E2E Tests
  run: pytest tests/e2e/ -v --tb=short

- name: Upload Coverage
  uses: codecov/codecov-action@v3
```

---

## 📚 Related Documentation

- [Architecture Guide](.github/instructions/architecture.instructions.md)
- [Testing Conventions](.github/instructions/testing.instructions.md)
- [API Conventions](.github/instructions/api-conventions.instructions.md)
- [Security Patterns](.github/instructions/security.instructions.md)

---

## ✅ Test Checklist

Before merging:

- [ ] All tests pass locally
- [ ] Coverage ≥95%
- [ ] No skipped tests (unless documented)
- [ ] Performance within targets
- [ ] No flaky tests
- [ ] Tests added for new features
- [ ] E2E tests cover critical paths

---

**Last Updated**: February 10, 2026
**Test Count**: 38 tests across 7 files
**Coverage Target**: 95%
