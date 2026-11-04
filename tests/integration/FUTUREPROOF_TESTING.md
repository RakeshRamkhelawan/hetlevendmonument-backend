# Futureproof Integration Test Framework

## Overview

The SanskritiSetu integration test suite now uses a **schema-based validation framework** that prevents:

- ✅ **KeyError exceptions** - Response fields are validated before access
- ✅ **Silent API contract violations** - Framework detects when API response format changes
- ✅ **Test brittleness** - Tests fail fast with clear error messages
- ✅ **Response format regressions** - Schema registry documents all API contracts

## Quick Start

### Basic Authenticated Test

```python
@pytest.mark.asyncio
async def test_get_agent(authenticated_api):
    """Simple GET with validation"""
    agent = await authenticated_api.get("/api/v1/agents/1", "agent")

    # Safe to access - schema validated
    assert agent["id"] == 1
    assert agent["name"]
```

### Create Resource

```python
@pytest.mark.asyncio
async def test_create_agent(authenticated_api):
    """POST with validation"""
    new_agent = await authenticated_api.post(
        "/api/v1/agents",
        {"name": "NewAgent", "type": "specialist"},
        schema_type="agent"
    )

    # Safe - schema validated these fields exist
    agent_id = new_agent["id"]
    assert new_agent["name"] == "NewAgent"
```

### List Resources

```python
@pytest.mark.asyncio
async def test_list_agents(authenticated_api):
    """GET list with validation"""
    result = await authenticated_api.get(
        "/api/v1/agents/",
        schema_type="agent_list"
    )

    # Safe - schema validated
    assert isinstance(result["data"], list)
    for agent in result["data"]:
        assert agent["id"]
        assert agent["name"]
```

## How It Works

### 1. Fixtures (conftest.py)

Three fixtures for different scenarios:

```python
# Fixture 1: Unauthenticated API helper
async def test_endpoint(api):
    # First, login
    token = await api.login("user@test.com", "password")
    # Then, use api.headers automatically set
    result = await api.get("/endpoint", "schema_type")

# Fixture 2: Already authenticated
async def test_endpoint(authenticated_api):
    # Already logged in, ready to go
    result = await authenticated_api.get("/endpoint", "schema_type")

# Fixture 3: Direct AsyncClient (for special cases)
async def test_endpoint(async_client):
    response = await async_client.get("/endpoint")
    # Manual validation if needed
```

### 2. Response Validation (response_validation.py)

All API responses are validated against schemas:

```python
from tests.integration.response_validation import (
    validate_response,
    assert_response_ok,
    ResponseValidationError,
)

# Automatic validation
data = validate_response(response, "agent", endpoint="/api/v1/agents/1")
# Returns validated dict, raises ResponseValidationError if schema mismatch

# Quick validation
assert_response_ok(response, endpoint="/endpoint")
# Validates status is 2xx and response is JSON
```

### 3. Schema Registry (response_validation.py)

Central registry defining all API response contracts:

```python
class ResponseSchema(Enum):
    AGENT = {
        "required": ["id", "name", "type", "status"],
        "optional": ["description", "created_at"]
    }

    AGENT_LIST = {
        "required": ["data"],
        "optional": ["page", "total"]
    }

    # ... more schemas ...

RESPONSE_SCHEMAS = {
    "/api/v1/agents": ResponseSchema.AGENT_LIST,
    "/api/v1/agents/{id}": ResponseSchema.AGENT,
    # ... endpoint mappings ...
}
```

## Files Overview

### Core Framework

| File | Purpose |
|------|---------|
| [tests/integration/response_validation.py](response_validation.py) | Schema definitions & validation logic |
| [tests/integration/conftest.py](conftest.py) | Fixtures including APIHelper class |
| [tests/integration/testing_guidelines.py](testing_guidelines.py) | Best practices documentation |
| [tests/integration/test_futureproof_example.py](test_futureproof_example.py) | 7 runnable examples |

### Existing Test Suites

| File | Status | Notes |
|------|--------|-------|
| [test_sprint1_onboarding_auth.py](test_sprint1_onboarding_auth.py) | ✅ 5/5 PASSING | Uses response validation framework |
| test_sprint2_specialist_agents.py | ⚠️ Needs migration | Uses old `response.json()["field"]` pattern |
| test_sprint3_workflows.py | ⚠️ Needs migration | Same pattern as Sprint 2 |
| test_sprint4_rag_tools.py | ⚠️ Needs migration | Same pattern as Sprint 2 |
| test_sprint5_hardening.py | ⚠️ Needs migration | Same pattern as Sprint 2 |

## API Helper Class

The `APIHelper` class provides all common HTTP operations with validation:

### Methods

```python
# Login and set auth headers
token_data = await api.login(email, password)

# GET with optional validation
data = await api.get(endpoint, schema_type="agent")

# POST with optional validation
data = await api.post(endpoint, json={...}, schema_type="agent")

# PATCH with optional validation
data = await api.patch(endpoint, json={...}, schema_type="agent")

# DELETE
response = await api.delete(endpoint)

# Properties
api.headers  # Current auth headers (or empty dict)
```

### Features

- **Automatic auth header management** - Login sets `api.headers["Authorization"]`
- **Schema validation** - All methods accept optional `schema_type` parameter
- **Consistent error handling** - All methods call `assert_response_ok()`
- **Clear error messages** - ResponseValidationError shows exact schema violation

## Adding New Endpoints

When you create a new API endpoint, add its schema:

### Step 1: Define Response Schema

In [response_validation.py](response_validation.py), add to `ResponseSchema` enum:

```python
class ResponseSchema(Enum):
    # ... existing schemas ...

    # New schema for your endpoint
    MY_NEW_ENDPOINT = {
        "required": ["id", "name", "status"],
        "optional": ["description", "created_at"]
    }
```

### Step 2: Register Endpoint Pattern

Still in `response_validation.py`, add to `RESPONSE_SCHEMAS` dict:

```python
RESPONSE_SCHEMAS = {
    # ... existing mappings ...

    "/api/v1/my-endpoint": ResponseSchema.MY_NEW_ENDPOINT,
    "/api/v1/my-endpoint/{id}": ResponseSchema.MY_NEW_ENDPOINT,  # Same schema for GET by ID
}
```

### Step 3: Use in Tests

Now all tests can use the validation:

```python
@pytest.mark.asyncio
async def test_my_endpoint(authenticated_api):
    result = await authenticated_api.get(
        "/api/v1/my-endpoint/123",
        "my_new_endpoint"
    )
    # All required fields guaranteed to exist
    assert result["id"] == 123
    assert result["name"]
```

## Migrating Old Tests

### Before (Fragile)

```python
@pytest.mark.asyncio
async def test_agent(async_client, auth_headers):
    response = await async_client.get("/api/v1/agents/1", headers=auth_headers)
    assert response.status_code == 200

    agent = response.json()  # ❌ No validation
    assert agent["id"] == 1  # ❌ KeyError if field missing
    assert agent["name"]     # ❌ KeyError if field missing
```

### After (Futureproof)

```python
@pytest.mark.asyncio
async def test_agent(authenticated_api):
    # ✅ Automatic validation on every call
    agent = await authenticated_api.get("/api/v1/agents/1", "agent")

    # ✅ Schema-validated - fields guaranteed to exist
    assert agent["id"] == 1
    assert agent["name"]
```

### Migration Checklist

- [ ] Replace `async_client.get()` with `api.get(..., "schema_type")`
- [ ] Replace `async_client.post()` with `api.post(..., "schema_type")`
- [ ] Remove manual `response.status_code` checks (APIHelper does it)
- [ ] Replace `response.json()["field"]` with validated `data["field"]`
- [ ] Use `authenticated_api` fixture instead of manual login
- [ ] Run test - schema validation catches any response format issues

## Error Handling

### ResponseValidationError

Raised when response doesn't match schema:

```python
try:
    agent = await api.get("/api/v1/agents/1", "agent")
except ResponseValidationError as e:
    # Output example:
    # "Missing required field 'name' in response from /api/v1/agents/1"
    # "Extra field 'extra_field' not in schema"
    print(e)
```

### AssertionError from assert_response_ok()

Raised when response is not 2xx or not JSON:

```python
response = await api.client.get("/api/v1/agents/999")

# Not caught by api.get() since no schema provided
# You can validate it yourself:
try:
    assert_response_ok(response)
except AssertionError:
    # Response was 404 or not JSON
    pass
```

## Common Patterns

### Check if Resource Exists

```python
async def test_get_nonexistent(authenticated_api):
    response = await authenticated_api.client.get(
        "/api/v1/agents/99999",
        headers=authenticated_api.headers
    )

    # Status is 404, not an error from our helper
    assert response.status_code == 404
```

### Create and Verify

```python
async def test_create_and_fetch(authenticated_api):
    # Create
    created = await authenticated_api.post(
        "/api/v1/agents",
        {"name": "Test"},
        "agent"
    )

    # Fetch - verify it was created
    fetched = await authenticated_api.get(
        f"/api/v1/agents/{created['id']}",
        "agent"
    )

    assert fetched["id"] == created["id"]
    assert fetched["name"] == created["name"]
```

### List and Filter

```python
async def test_list_agents(authenticated_api):
    result = await authenticated_api.get(
        "/api/v1/agents/?type=specialist",
        "agent_list"
    )

    # Data field validated by schema
    for agent in result["data"]:
        if agent["type"] == "specialist":
            assert agent["type"] == "specialist"
```

## Test Execution

### Run All Integration Tests

```bash
pytest tests/integration/ -v
```

### Run with Coverage

```bash
pytest tests/integration/ --cov=src --cov-report=html
```

### Run Specific Test File

```bash
pytest tests/integration/test_futureproof_example.py -v
```

### Run Specific Test

```bash
pytest tests/integration/test_futureproof_example.py::test_get_agent_with_validation -v
```

## Common Errors & Solutions

### Error: `ResponseValidationError: No schema defined for endpoint`

**Cause:** Schema not in registry

**Fix:** Add to `response_validation.py`:

```python
# In ResponseSchema enum:
YOUR_ENDPOINT = {"required": ["fields"], "optional": [...]}

# In RESPONSE_SCHEMAS dict:
"/api/v1/your-endpoint": ResponseSchema.YOUR_ENDPOINT,
```

### Error: `KeyError: 'id'` in line `agent_id = response.json()["id"]`

**Cause:** Using old pattern without validation

**Fix:** Use validated response:

```python
# Old (fragile)
agent_id = response.json()["id"]  # ❌

# New (futureproof)
agent = await api.get("/api/v1/agents/1", "agent")
agent_id = agent["id"]  # ✅
```

### Error: `AssertionError: Response status 401`

**Cause:** Not authenticated

**Fix:** Use `authenticated_api` fixture:

```python
# Without auth
async def test_endpoint(api):
    # Need to login first
    token = await api.login("user@test.com", "password")
    # api.headers now set
    data = await api.get("/endpoint", "schema")

# With auth
async def test_endpoint(authenticated_api):
    # Already logged in
    data = await authenticated_api.get("/endpoint", "schema")
```

## Best Practices

### DO ✅

1. **Always use schema validation**
   ```python
   data = await api.get(endpoint, "agent")  # ✅ Validated
   ```

2. **Use authenticated_api fixture for protected endpoints**
   ```python
   async def test_protected(authenticated_api):  # ✅
       data = await authenticated_api.get("/protected", "schema")
   ```

3. **Define schemas for all response types**
   ```python
   class ResponseSchema(Enum):
       NEW_TYPE = {"required": [...], "optional": [...]}  # ✅
   ```

4. **Use APIHelper methods for all requests**
   ```python
   await authenticated_api.post(endpoint, json, "schema")  # ✅
   ```

### DON'T ❌

1. **Direct JSON access without validation**
   ```python
   data = response.json()["field"]  # ❌ No validation
   ```

2. **Assume fields exist**
   ```python
   assert agent["name"]  # ❌ May KeyError if schema wrong
   ```

3. **Manual login in every test**
   ```python
   async def test_x(async_client):  # ❌ Tedious
       response = await async_client.post("/auth/login", ...)
   ```

4. **Catch KeyError instead of using validation**
   ```python
   try:
       field = response.json()["field"]
   except KeyError:  # ❌ Hides real issue
       pass
   ```

## Testing the Framework

### Run Example Tests

```bash
# All 7 examples demonstrate the framework
pytest tests/integration/test_futureproof_example.py -v
```

### Run Sprint 1 Tests (All Passing)

```bash
# These use the framework and all pass
pytest tests/integration/test_sprint1_onboarding_auth.py -v
```

### Run Full Suite

```bash
pytest tests/integration/test_sprint*.py -v
```

## Architecture

```
Integration Test Framework
├── response_validation.py
│   ├── ResponseSchema enum (10+ schemas)
│   ├── validate_response() function
│   ├── assert_response_ok() function
│   └── RESPONSE_SCHEMAS registry
│
├── conftest.py
│   ├── APIHelper class
│   ├── api fixture (unauthenticated)
│   └── authenticated_api fixture
│
├── testing_guidelines.py
│   ├── Best practices documentation
│   ├── Common patterns
│   └── Error handling examples
│
└── test_futureproof_example.py
    ├── 7 runnable examples
    └── Common patterns demonstrated
```

## Files Summary

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| response_validation.py | 250+ | Schema definitions & validation | ✅ Complete |
| conftest.py | 1750+ | Fixtures & APIHelper class | ✅ Complete |
| testing_guidelines.py | 200+ | Best practices documentation | ✅ Complete |
| test_futureproof_example.py | 350+ | 7 runnable examples | ✅ Complete |
| test_sprint1*.py | 240+ | Framework-using tests | ✅ PASSING |
| test_sprint2*.py | | Need schema migration | ⏳ TODO |

## Contributing

When adding new tests:

1. ✅ Use `authenticated_api` fixture
2. ✅ Validate all responses with schema_type
3. ✅ Use `APIHelper` methods (get, post, patch, delete)
4. ✅ Add schemas to `response_validation.py` if needed
5. ✅ Follow naming convention: `test_<feature>_<scenario>`

## Support

For questions about the framework:

1. Check [testing_guidelines.py](testing_guidelines.py) for patterns
2. See [test_futureproof_example.py](test_futureproof_example.py) for examples
3. Review [response_validation.py](response_validation.py) for schema definitions
4. Check existing passing tests in [test_sprint1_onboarding_auth.py](test_sprint1_onboarding_auth.py)

---

**Last Updated:** 2025-01-29
**Framework Status:** ✅ Production Ready
**Test Coverage:** 5/31 tests passing (Sprint 1 100%, Sprints 2-5 need migration)
