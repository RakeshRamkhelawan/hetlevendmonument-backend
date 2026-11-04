---
description: Testing conventions and patterns for SanskritiSetu
applyTo: 'tests/**'
---

# Testing Instructions

## ⚡ QUICK REFERENCE

### 🚫 Common Test Failures - Quick Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: core` | Wrong import | `from src.core.X` not `from core.X` |
| `No data found` | Tenant filter | Use `TenantFilterBypass()` or `isolated_tenant` |
| `MLflow connection timeout` | Mock not loaded | MLflow mock in conftest.py must be FIRST |
| `Event loop closed` | Missing decorator | Add `@pytest.mark.asyncio` |
| `Duplicate key` | ID collision | Use `TenantFactory.next_id()` |
| `Stale auth` | Override pollution | `isolate_dependency_overrides` fixture handles this |

### 🔑 Essential Fixtures

```python
# Most common fixtures you'll need:
def test_api(test_client, test_user_with_token):
    token = test_user_with_token["token"]
    response = test_client.get("/api/...", headers={"Authorization": f"Bearer {token}"})

@pytest.mark.asyncio
async def test_db(async_db_session, test_user):
    tenant_id = test_user["tenant_id"]
    # async_db_session auto-commits and rolls back
```

### 📋 Run Commands

```powershell
python -m pytest tests/unit/ -v --tb=short     # Unit tests
python -m pytest tests/unit/test_X.py -x       # Single file, stop on fail
python -m pytest tests/ --cov=src              # With coverage
```

---

## Test Structure
```
tests/
├── unit/           # Fast, isolated tests (no external deps)
├── integration/    # Tests with database/services
├── chaos/          # Resilience testing
├── security/       # Security-specific tests
└── conftest.py     # Shared fixtures (CRITICAL FILE)
```

## Running Tests

```powershell
# Unit tests only (fast, default)
python -m pytest tests/unit/ -v --tb=short

# With coverage
python -m pytest tests/unit/ --cov=src --cov-fail-under=80

# Specific test file
python -m pytest tests/unit/test_auth.py -v

# Integration tests (requires Docker services)
docker-compose -f docker-compose.dev.yml up -d
python -m pytest tests/integration/ -v

# Stop after first failure
python -m pytest tests/unit/ -x
```

## Critical: conftest.py Patterns

### MLflow Mock MUST Be First
```python
# tests/conftest.py - Lines 20-58
# CRITICAL: MLflow Mock MUST be FIRST before any imports
import sys
from unittest.mock import MagicMock

_mlflow_mock = MagicMock()
sys.modules['mlflow'] = _mlflow_mock
# This prevents network calls during app initialization
```

### Path Setup
```python
# Ensures src.core imports work
from pathlib import Path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))
```

## Test Fixtures (from conftest.py)

### Available Fixtures
| Fixture | Scope | Description |
|---------|-------|-------------|
| `async_engine` | session | Single engine for all tests (performance) |
| `async_db_session` | function | Auto-cleanup async SQLAlchemy session |
| `test_client` | function | FastAPI TestClient with mocked auth |
| `test_tenant` | function | Pre-created tenant (returns ID) |
| `test_role` | function | Pre-created role for tenant |
| `test_user` | function | Pre-created user with role |
| `test_user_with_token` | function | User dict including JWT token |
| `isolated_tenant` | function | Completely isolated tenant/role/user set |

### TenantFactory for Unique IDs
```python
# Use TenantFactory for unique IDs (prevents collisions)
from tests.conftest import TenantFactory

tenant_id = TenantFactory.next_id()  # Thread-safe, starts at 10000
role_id = TenantFactory.next_id()
user_id = TenantFactory.next_id()
```

### Usage Example
```python
@pytest.mark.asyncio
async def test_create_workflow(async_db_session, test_user):
    """Test workflow creation with real fixtures."""
    user_id = test_user["id"]
    tenant_id = test_user["tenant_id"]

    # Your test logic here
    assert result is not None
```

## Dependency Override Isolation (CRITICAL)

### The Problem
Multiple tests can pollute `app.dependency_overrides`, causing auth failures.

### The Solution (auto-applied)
```python
# conftest.py has this autouse fixture:
@pytest.fixture(scope="function", autouse=True)
def isolate_dependency_overrides(app: FastAPI):
    """Each test gets fresh dependency_overrides"""
    app.dependency_overrides.clear()  # Clear before
    yield
    app.dependency_overrides.clear()  # Clear after
```

### Manual Override in Tests
```python
def test_with_mock_auth(test_client, app):
    # Override for this test only
    app.dependency_overrides[get_current_user] = lambda: mock_user

    response = test_client.get("/protected")

    # Cleanup happens automatically via fixture
```

## Mocking Strategy

### MLflow (Auto-mocked)
```python
# No action needed - MLflow calls won't hit real servers
import mlflow  # This is already a MagicMock in tests
```

### External Services Markers
```python
@pytest.mark.requires_redis
def test_cache_functionality():
    """Only runs if Redis is available."""
    pass

@pytest.mark.requires_rabbitmq
def test_message_queue():
    """Only runs if RabbitMQ is available."""
    pass

@pytest.mark.requires_mlflow
def test_mlflow_tracking():
    """Skipped by default (MLflow is mocked)."""
    pass
```

## Tenant Isolation in Tests

### Problem: Auto-filtering
The `TenantMiddleware` auto-filters queries by `tenant_id`. In tests, this can cause "no data found" errors.

### Solution: TenantFilterBypass
```python
from src.core.middleware.tenant_context import TenantFilterBypass

async def test_admin_operation(async_db_session):
    # Bypass tenant filter for admin/setup operations
    with TenantFilterBypass():
        result = await async_db_session.execute(select(User))
        users = result.scalars().all()
```

### Solution: Use isolated_tenant Fixture
```python
@pytest.mark.asyncio
async def test_with_isolation(isolated_tenant):
    """Uses completely isolated tenant with unique IDs."""
    tenant_id = isolated_tenant["tenant_id"]
    user = isolated_tenant["user"]
    # All IDs are unique, no collisions
```

## Common Test Patterns

### Testing Endpoints
```python
def test_endpoint_success(test_client, test_user_with_token):
    token = test_user_with_token["token"]
    response = test_client.get(
        "/api/v1/workflows/",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
```

### Testing with Database
```python
@pytest.mark.asyncio
async def test_db_operation(async_db_session):
    # Session auto-commits and rolls back after test
    workflow = Workflow(name="test", tenant_id=1)
    async_db_session.add(workflow)
    await async_db_session.flush()

    assert workflow.id is not None
```

### Testing Error Cases
```python
def test_not_found(test_client, test_user_with_token):
    token = test_user_with_token["token"]
    response = test_client.get(
        "/api/v1/workflows/99999",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404
```

## Performance Tips

### DO: Session-scoped Engine
```python
# CORRECT: Engine created once per test session
@pytest_asyncio.fixture(scope="session")
async def async_engine():
    engine = create_async_engine(...)
    yield engine
```

### DON'T: Function-scoped Engine
```python
# WRONG: Creates new engine for EVERY test (slow!)
@pytest.fixture(scope="function")
async def engine():
    engine = create_async_engine(...)  # 0.5-3s overhead per test!
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Table not found" | Run `alembic upgrade head` first |
| "Tenant filter empty" | Use `TenantFilterBypass()` context |
| "MLflow timeout" | MLflow is mocked - check import order in conftest |
| "Event loop error" | Ensure `@pytest.mark.asyncio` decorator |
| "Import error" | Use `python -m pytest` (not just `pytest`) |
| "Stale overrides" | `isolate_dependency_overrides` fixture should handle this |
| "ID collision" | Use `TenantFactory.next_id()` for unique IDs |
