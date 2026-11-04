# Test Fixtures Usage Guide

## Shared App Fixture

All tests now use a **shared FastAPI app** that matches `main.py` exactly.

### ❌ OLD WAY (causes 404 errors)

```python
from fastapi import FastAPI
from core.api.auth_endpoints import router

app = FastAPI()
app.include_router(router, prefix="/api/auth")  # Wrong!
client = TestClient(app)
```python

### ✅ NEW WAY (use shared fixture)

```python

def test_register_user(client):  # Uses shared app fixture
    response = client.post("/api/auth/register_user", json={...})
    assert response.status_code == 201
```python

## Available Fixtures

### 1. `app` - Shared FastAPI Application

```python

def test_something(app):

    # app has ALL routers registered (matches main.py)

    assert "/api/auth/register_user" in [route.path for route in app.routes]
```python

### 2. `client` - Synchronous Test Client

```python

def test_api_endpoint(client):
    response = client.get("/api/agents")
    assert response.status_code == 200
```python

### 3. `async_client` - Async Test Client

```python

async def test_async_endpoint(async_client):
    response = await async_client.get("/api/agents")
    assert response.status_code == 200
```python

### 4. `auth_headers` - Authenticated Headers

```python

def test_protected_endpoint(client, auth_headers):
    response = client.get("/api/protected", headers=auth_headers)
    assert response.status_code == 200
```python

### 5. `admin_auth_headers` - Admin Headers

```python

def test_admin_endpoint(client, admin_auth_headers):
    response = client.get("/api/admin/users", headers=admin_auth_headers)
    assert response.status_code == 200
```python

### 6. `db_session` - Database Session

```python

async def test_with_db(db_session):
    from core.database.models import User
    user = User(email="test@example.com")
    db_session.add(user)
    await db_session.commit()
```python

### 7. `redis_client` - Mock Redis

```python

async def test_cache(redis_client):
    await redis_client.set("key", "value")
    assert await redis_client.get("key") == "value"
```python

### 8. `mock_event_publisher` - Auto-Applied

No need to import - automatically mocks RabbitMQ for all tests!

## Migration Checklist

For each test file:

1. **Remove custom app creation**
   - Delete: `app = FastAPI()`
   - Delete: `app.include_router(...)`
   - Delete: `client = TestClient(app)`

2. **Add `client` fixture parameter**

   ```python
   def test_something(client):  # <-- Add this
       response = client.post(...)
```python

3. **Check route paths**
   - Ensure paths match main.py registration
   - Example: `/api/auth/register_user` (not `/api/auth/api/auth/register_user`)

4. **Add auth headers when needed**

   ```python

   def test_protected(client, auth_headers):
       response = client.get("/api/protected", headers=auth_headers)
```python

## Quick Fix Template

```python

# OLD

app = FastAPI()
app.include_router(router, prefix="/api/auth")
client = TestClient(app)

def test_something():
    response = client.post("/api/auth/endpoint", json={...})

# NEW

def test_something(client):  # Use fixture
    response = client.post("/api/auth/endpoint", json={...})

```python

## Benefits

- ✅ No 404 errors from inconsistent routing
- ✅ Tests match production app exactly
- ✅ Authentication mocked automatically
- ✅ Faster test execution (shared app)
- ✅ Easier maintenance (one source of truth)
