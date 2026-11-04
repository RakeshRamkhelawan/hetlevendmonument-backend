---
description: Security patterns including JWT, RBAC, and tenant isolation
applyTo: 'src/core/**'
---

# Security Instructions

## Multi-Tenant Architecture (CRITICAL)

### Every Model MUST Have tenant_id

```python
from sqlalchemy import Column, Integer, ForeignKey
from src.core.database.database import Base

class YourModel(Base):
    __tablename__ = "your_models"

    id = Column(Integer, primary_key=True)

    # REQUIRED for tenant isolation
    tenant_id = Column(
        Integer,
        ForeignKey('tenants.id', ondelete='CASCADE'),
        nullable=False,  # Never nullable!
        index=True       # Always indexed for performance
    )

    # Your other columns...
```

### Anti-Pattern (Data Leak Risk!)

```python
# WRONG: String type, nullable, no FK
tenant_id = Column(String(100), nullable=True, index=True)

# WRONG: Missing tenant_id entirely
class UnsafeModel(Base):
    id = Column(Integer, primary_key=True)
    name = Column(String)  # No tenant_id = data leak!
```

## Tenant Auto-Filtering

The `TenantMiddleware` + `tenant_query_filter.py` automatically filter all queries:

```python
# This query is AUTOMATICALLY filtered by tenant_id
users = await session.execute(select(User))
# Actually executes: SELECT * FROM users WHERE tenant_id = <current_tenant>
```

### Bypass for Admin Operations

```python
from src.core.middleware.tenant_context import TenantFilterBypass

# When you need to bypass (admin/system operations)
with TenantFilterBypass():
    all_tenants = await session.execute(select(Tenant))
    # No tenant filter applied
```

### Get Current Tenant ID

```python
from src.core.middleware.tenant_context import get_tenant_id, require_tenant_id

# Optional (returns None if not set)
tenant_id = get_tenant_id()

# Required (raises 403 if not set) - USE THIS
tenant_id = require_tenant_id()
```

## JWT Token Handling

### Token Structure

```python
# Standard JWT payload structure
{
    "sub": "user@example.com",      # Primary identifier
    "tenant_id": 123,               # REQUIRED for multi-tenant
    "role": "admin",                # User's role
    "exp": 1702234567               # Expiration timestamp
}
```

### Supported Token Formats (for backwards compatibility)

```python
# The system accepts these formats:
# Format 1: {"sub": "user@example.com"}
# Format 2: {"email": "user@example.com"}
# Format 3: {"user_id": "user_email@example.com"}
```

### Creating Tokens

```python
from src.core.auth.jwt_handler import create_access_token

token = create_access_token(
    data={
        "sub": user.email,
        "tenant_id": user.tenant_id,
        "role": user.role.name
    },
    expires_delta=timedelta(hours=24)
)
```

### Validating Tokens in Endpoints

```python
from src.core.auth.dependencies import get_current_user, require_admin

@router.get("/protected")
async def protected_endpoint(
    current_user: User = Depends(get_current_user)
):
    """Standard authenticated endpoint."""
    return {"user_id": current_user.id}

@router.delete("/admin-only")
async def admin_endpoint(
    current_user: User = Depends(require_admin)
):
    """Requires admin role."""
    pass
```

## RBAC (Role-Based Access Control)

### Default Role Permissions

| Role | Permissions |
|------|-------------|
| `user` | READ |
| `moderator` | READ, WRITE |
| `admin` | READ, WRITE, ADMIN, SYSTEM_MONITOR |
| `system_admin` | READ, WRITE, ADMIN, SYSTEM_MONITOR, SYSTEM_ADMIN, LOG_ANALYZER |

### Checking Permissions

```python
from src.core.auth.scope_validator import ScopeValidator

# Check if user has required permission
validator = ScopeValidator()
if not validator.has_permission(current_user, "admin"):
    raise HTTPException(status_code=403, detail="Admin access required")
```

## Excluded Paths (No Auth Required)

These paths bypass authentication:

```python
EXCLUDED_PATHS = {
    "/",
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
}
```

## Rate Limiting

```python
from src.core.middleware.rate_limiter import get_limiter

limiter = get_limiter()

@router.get("/limited")
@limiter.limit("10/minute")
async def rate_limited_endpoint():
    pass
```

Default limits: `100/minute` per IP address.

## Security Headers

The `SecurityHeadersMiddleware` adds:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security` (in production)

## Egress Control

### Egress-Aware HTTP Client

Gebruik `EgressAwareAsyncClient` voor alle outbound HTTP calls van agents/services:

```python
from src.core.security.egress_aware_client import EgressAwareAsyncClient
from src.core.security.egress_control import EgressController

# Feature-flagged: alleen actief als FEATURE_FLAG_EGRESS_CONTROL=true
controller = EgressController()
client = EgressAwareAsyncClient(
    egress_controller=controller,
    tenant_id=current_tenant_id,
    agent_id=agent_id,
)

async with client:
    response = await client.request("GET", "https://api.trusted.com/data")
```

### Egress in ActivePieces Client

`ActivePiecesClient` heeft egress controle ingebouwd (feature-flagged):

```python
from src.core.activepieces.client import ActivePiecesClient
from src.core.security.egress_control import EgressController

controller = EgressController()
client = ActivePiecesClient(egress_controller=controller)
# _authenticate() en _make_request() valideren URL automatisch
```

**Waarschuwing:** Andere HTTP clients (LLM providers, externe APIs) moeten ook `EgressAwareAsyncClient` gebruiken voor consistente egress policy enforcement.

## Common Security Mistakes

### 1. Forgetting Tenant Filter

```python
# WRONG: No tenant check (data leak!)
user = await session.get(User, user_id)

# CORRECT: Explicit tenant check
user = await session.get(User, user_id)
if user.tenant_id != current_user.tenant_id:
    raise HTTPException(status_code=404, detail="User not found")
```

### 2. Exposing Internal Errors

```python
# WRONG: Exposes stack trace
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))

# CORRECT: Generic message + logging
except Exception as e:
    logger.error(f"Operation failed: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")
```

### 3. Missing Authentication

```python
# WRONG: Endpoint without auth
@router.get("/sensitive-data")
async def get_sensitive():
    return {"secret": "data"}

# CORRECT: Require authentication
@router.get("/sensitive-data")
async def get_sensitive(user: User = Depends(get_current_user)):
    return {"secret": "data"}
```

### 4. Placeholder Secrets in Production

```python
# WRONG: Placeholder secret in .env wordt niet gedetecteerd
SECRET_KEY="your-secret-key-change-in-production"

# CORRECT: ConfigValidator blokkeert startup bij placeholders in productie
# Zet een echte secret (minimaal 32 karakters)
SECRET_KEY="$(openssl rand -hex 32)"
```
