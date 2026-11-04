# 🧪 SanskritiSetu Testing Guide

**Moderne pytest setup voor snelle, geïsoleerde,en onderhoudbare tests**

## 📋 Inhoudsopgave

- [Quick Start](#quick-start)
- [Test Architectuur](#test-architectuur)
- [Fixture Systeem](#fixture-systeem)
- [Test Markers](#test-markers)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### Alle tests draaien

```powershell
# Volledige testsuite
pytest

# Alleen unit tests (snel, >90% van testsuite)
pytest -m unit

# Alleen integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

### Specifieke tests draaien

```powershell
# Een enkel bestand
pytest tests/unit/test_auth_endpoints.py

# Een enkele test class
pytest tests/unit/test_auth_endpoints.py::TestAuthEndpoints

# Een enkele test functie
pytest tests/unit/test_auth_endpoints.py::TestAuthEndpoints::test_login_success

# Alle tests met "auth" in de naam
pytest -k "auth"
```

### Development workflow

```powershell
# Quick feedback loop (stop na eerste failure)
pytest tests/unit/ -x

# Verbose output met korte tracebacks
pytest tests/unit/ -v --tb=short

# Alleen failures tonen
pytest tests/unit/ -v --tb=short -ra
```

---

## 🏗️ Test Architectuur

### Directory Structuur

```
tests/
├── conftest.py                  # Root configuratie (MINIMAAL - laadt alleen fixtures)
├── fixtures/                    # Herbruikbare fixtures (MODULAR)
│   ├── api.py                  # FastAPI app & test client
│   ├── auth.py                 # Authenticatie fixtures (users, tokens)
│   ├── database.py             # Database sessies & factories
│   ├── tenant.py               # Tenant & multi-tenancy fixtures
│   ├── mocks.py                # 3rd party service mocks
│   ├── agent_mocks.py          # AI agent mocks
│   ├── llm_mocks.py            # LLM provider mocks
│   └── README.md               # Fixture documentatie
├── unit/                        # Unit tests (FAST, ISOLATED)
│   ├── test_auth_endpoints.py
│   ├── test_user_endpoints.py
│   └── repositories/
│       └── test_user_repository.py
├── integration/                 # Integration tests (DATABASE, EXTERNAL SERVICES)
│   ├── test_workflow_engine.py
│   └── test_agent_orchestration.py
└── e2e/                         # End-to-end tests (FULL STACK)
    └── test_user_journey.py
```

### Geïsoleerde Test Setup

**Elk test krijgt:**
- ✅ Nieuwe FastAPI app instance
- ✅ Nieuwe database sessie (in-memory SQLite)
- ✅ Schone tenant context
- ✅ Gemockte externe dependencies

**Dit voorkomt:**
- ❌ Test pollution (tests beïnvloeden elkaar)
- ❌ Race conditions (concurrent tests)
- ❌ Flaky tests (onvoorspelbare failures)

---

## 🎯 Fixture Systeem

### Core Fixtures

#### 1. `test_client` - FastAPI Test Client

```python
@pytest.mark.asyncio
async def test_list_users(test_client):
    """
    test_client is een geïsoleerde FastAPI app instance.
    - Volledig configureerde app
    - Database overrides actief
    - Middleware stack geladen
    """
    response = await test_client.get("/api/v1/users")
    assert response.status_code == 200
```

**Belangrijke features:**
- Async HTTP client (httpx.AsyncClient)
- Automatisch database dependency override
- Geïsoleerd per test function

#### 2. `db_session` - Database Sessie

```python
@pytest.mark.asyncio
async def test_create_user(db_session, tenant_factory):
    """
    db_session is een SQLAlchemy AsyncSession.
    - In-memory SQLite (geen PostgreSQL nodig voor unit tests)
    - Automatisch rollback na test
    - Tenant filtering actief
    """
    tenant = await tenant_factory.create_tenant()

    user = User(
        email="test@example.com",
        tenant_id=tenant["id"]
    )
    db_session.add(user)
    await db_session.commit()

    # Verify
    result = await db_session.execute(
        select(User).where(User.email == "test@example.com")
    )
    assert result.scalar_one() is not None
```

#### 3. `tenant_factory` - Tenant Factory

```python
async def test_multi_tenant_isolation(db_session, tenant_factory):
    """
    tenant_factory maakt test tenants aan.
    """
    tenant_a = await tenant_factory.create_tenant(slug="tenant-a")
    tenant_b = await tenant_factory.create_tenant(slug="tenant-b")

    # Each tenant is isolated
    assert tenant_a["id"] != tenant_b["id"]
```

#### 4. `test_user` & `test_admin_user` - Auth Fixtures

```python
async def test_protected_endpoint(test_client, test_user, test_token):
    """
    test_user: Regular user fixture
    test_admin_user: Admin user with elevated permissions
    test_token: Valid JWT token
    """
    response = await test_client.get(
        "/api/v1/protected",
        headers={"Authorization": f"Bearer {test_token}"}
    )
    assert response.status_code == 200
```

###Mock Fixtures

#### 5. `fake_llm_provider` - LLM Mock

```python
def test_agent_with_mock_llm(fake_llm_provider):
    """
    fake_llm_provider: Predictable LLM responses
    - No API calls
    - Fast
    - Deterministic
    """
    fake_llm_provider.set_response("What is AI?", "Artificial Intelligence")

    response = fake_llm_provider.generate("What is AI?")
    assert "Artificial Intelligence" in response
```

#### 6. `mock_redis_client` - Redis Mock

```python
async def test_caching(mock_redis_client):
    """
    mock_redis_client: In-memory Redis behavior
    - No Redis server needed
    - Fast
    - Isolated per test
    """
    await mock_redis_client.set("key", "value")
    result = await mock_redis_client.get("key")
    assert result == "value"
```

### Fixture Composability

Fixtures kunnen worden gecombineerd:

```python
async def test_complex_workflow(
    test_client,
    db_session,
    tenant_factory,
    test_admin_user,
    test_token,
    fake_llm_provider
):
    """
    Combineer multiple fixtures voor realistische scenarios.
    """
    # Setup
    tenant = await tenant_factory.create_tenant()
    fake_llm_provider.set_response("Analyze", "Analysis complete")

    # Execute
    response = await test_client.post(
        "/api/v1/analyze",
        headers={"Authorization": f"Bearer {test_token}"},
        json={"text": "Sample"}
    )

    # Verify
    assert response.status_code == 200
```

---

## 🏷️ Test Markers

Markers categoriseren tests voor selectieve executie.

### Beschikbare Markers

| Marker | Beschrijving | Gebruik |
|--------|-------------|---------|
| `@pytest.mark.unit` | Snelle, geïsoleerde tests | Default voor meeste tests |
| `@pytest.mark.integration` | Tests met database/externe services | Complex workflows |
| `@pytest.mark.e2e` | End-to-end user flows | Full stack tests |
| `@pytest.mark.slow` | Tests >1 seconde | Performance tests |
| `@pytest.mark.smoke` | Kritieke happy path tests | CI/CD quick validation |
| `@pytest.mark.security` | Security & tenant isolation | RBAC, auth, isolation |
| `@pytest.mark.llm` | Tests met echte LLM API calls | Costly, slow |

### Marker Gebruik

```python
import pytest

@pytest.mark.unit
@pytest.mark.smoke
async def test_login_happy_path(test_client):
    """Quick smoke test for critical login flow."""
    response = await test_client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "password123"}
    )
    assert response.status_code == 200

@pytest.mark.integration
@pytest.mark.slow
async def test_workflow_execution(test_client, db_session):
    """Integration test for full workflow execution."""
    # Complex multi-step workflow test
    ...

@pytest.mark.llm
@pytest.mark.skip(reason="Expensive API calls - run manually")
async def test_real_gemini_api():
    """Test with real Gemini API (not run in CI)."""
    ...
```

### Markers Selecteren

```powershell
# Alleen smoke tests (CI quick check)
pytest -m smoke

# Alles behalve slow tests
pytest -m "not slow"

# Unit OF integration (maar niet e2e)
pytest -m "unit or integration"

# Security tests die niet slow zijn
pytest -m "security and not slow"

# Niets met LLM (voor lokaal development)
pytest -m "not llm"
```

---

## ✅ Best Practices

### 1. Test Isolatie

**✅ DO:**
```python
@pytest.mark.unit
async def test_create_user(db_session, tenant_factory):
    """Each test gets fresh database session."""
    tenant = await tenant_factory.create_tenant()
    user = User(email="test@example.com", tenant_id=tenant["id"])
    db_session.add(user)
    await db_session.commit()
    # Test completes, db_session auto-rollback
```

**❌ DON'T:**
```python
# Globale state die andere tests beïnvloedt
GLOBAL_USER = None

def test_create_global_user():
    global GLOBAL_USER
    GLOBAL_USER = User(...)  # ❌ Flaky tests!
```

### 2. Maak Fixtures met Factory Pattern

**✅ DO:**
```python
@pytest.fixture
def user_factory(db_session):
    """Factory voor flexibele test data."""
    async def _create_user(email=None, role="user"):
        user = User(
            email=email or f"user-{uuid4()}@example.com",
            role=role
        )
        db_session.add(user)
        await db_session.commit()
        return user
    return _create_user

async def test_with_custom_user(user_factory):
    admin = await user_factory(role="admin")
    assert admin.role == "admin"
```

**❌ DON'T:**
```python
@pytest.fixture
def hardcoded_user():
    """Hardcoded data = minder flexibel."""
    return User(email="fixed@example.com")  # ❌ Kan conflicteren
```

### 3. Test Naming

**✅ DO:**
```python
def test_login_with_valid_credentials_returns_jwt_token():
    """Clear, descriptive name describes scenario & expected outcome."""
    ...

def test_login_with_invalid_password_returns_401():
    """Easy to understand what's being tested."""
    ...
```

**❌ DON'T:**
```python
def test_auth():  # ❌ Te vaag
    ...

def test_1():  # ❌ Betekenisloos
    ...
```

### 4. AAA Pattern (Arrange-Act-Assert)

```python
async def test_user_creation(test_client, tenant_factory):
    # ARRANGE - Setup test data
    tenant = await tenant_factory.create_tenant()
    user_data = {
        "email": "newuser@example.com",
        "password": "SecurePass123",
        "tenant_id": tenant["id"]
    }

    # ACT - Execute the action being tested
    response = await test_client.post("/api/v1/users", json=user_data)

    # ASSERT - Verify the outcome
    assert response.status_code == 201
    assert response.json()["email"] == user_data["email"]
```

### 5. Mock Externe Dependencies

**✅ DO:**
```python
@pytest.mark.unit
async def test_send_email(mock_sendgrid_client):
    """Mock externe services voor unit tests."""
    await send_email("user@example.com", "Test")
    mock_sendgrid_client.assert_called_once_with(
        to="user@example.com",
        subject="Test"
    )
```

**❌ DON'T:**
```python
async def test_real_sendgrid():
    """Echte API calls in unit tests = slow, flaky, costly."""
    await real_sendgrid.send(...)  # ❌ Vermijd dit
```

---

## 🐛 Troubleshooting

### Problem: "fixture not found"

```
E   fixture 'test_client' not found
```

**Oplossing:** Zorg dat `tests/conftest.py` de fixture module laadt:

```python
# tests/conftest.py
pytest_plugins = [
    "tests.fixtures.api",  # <-- test_client is hier
    "tests.fixtures.auth",
    "tests.fixtures.database",
]
```

### Problem: "Module already imported" warnings

```
PytestAssertRewriteWarning: Module already imported so cannot be rewritten
```

**Oplossing:** Dit is een pytest warning die niet schadelijk is, maar kan worden gefilterd:

```toml
# pyproject.toml
[tool.pytest.ini_options]
filterwarnings = [
    "default::pytest.PytestAssertRewriteWarning",
]
```

### Problem: Tests falen met DatabaseError

```
DatabaseError: database is locked
```

**Oplossing:** SQLite connection pooling issue. Gebruik `NullPool`:

```python
# tests/fixtures/database.py
engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=NullPool,  # ✅ SQLite doesn't support pooling
)
```

### Problem: Tenant isolation niet actief

```
AssertionError: Expected 1 user, got 5
```

**Oplossing:** Zorg dat elke test een nieuwe database sessie krijgt:

```python
@pytest.fixture
async def db_session():
    """Function-scoped fixture voor volledige isolatie."""
    # Nieuwe sessie per test
    async with session_factory() as session:
        yield session
        await session.rollback()  # ✅ Cleanup
```

### Problem: Async fixture errors

```
TypeError: object AsyncGenerator can't be used in 'await' expression
```

**Oplossing:** Gebruik `pytest-asyncio` en `@pytest_asyncio.fixture`:

```python
import pytest_asyncio

@pytest_asyncio.fixture
async def async_resource():
    resource = await create_async_resource()
    yield resource
    await resource.cleanup()
```

---

## 📊 Coverage & Reporting

### Coverage Genereren

```powershell
# Basis coverage
pytest --cov=src

# HTML rapport
pytest --cov=src --cov-report=html

# Terminal rapport met missing lines
pytest --cov=src --cov-report=term-missing

# Coverage target (fail onder 80%)
pytest --cov=src --cov-fail-under=80
```

### JSON Test Rapport

```powershell
pytest --json-report --json-report-file=test-report.json
```

---

## 🚀 CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements-test.txt

      - name: Run unit tests (fast)
        run: |
          pytest -m "unit and not slow" --cov=src --cov-fail-under=80

  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4

      - name: Start PostgreSQL
        run: |
          docker-compose up -d postgres

      - name: Run integration tests
        run: |
          pytest -m integration --cov=src
```

---

## 📚 Aanvullende Resources

- **Fixture Library:** [tests/fixtures/README.md](fixtures/README.md)
- **Architecture Docs:** [.github/copilot-instructions.md](../.github/copilot-instructions.md)
- **pytest Docs:** https://docs.pytest.org/
- **pytest-asyncio:** https://pytest-asyncio.readthedocs.io/

---

**Laatste update:** Februari 2026
**Maintainer:** SanskritiSetu Development Team
