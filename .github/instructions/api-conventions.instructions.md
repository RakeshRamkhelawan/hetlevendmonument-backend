---
description: API conventions and endpoint patterns for SanskritiSetu
applyTo: 'src/core/api/**'
---

# API Conventions Instructions

## URL Structure

All API endpoints follow the `/api/v1/` prefix pattern:

```
/api/v1/workflows/       # Workflow management
/api/v1/agents/          # Agent operations
/api/v1/auth/            # Authentication
/api/v1/security/        # Security operations
/api/v1/tools/           # Tool broker
/api/v1/subagents/       # Subagent management
```

**Exceptions** (legacy/special):
```
/rbac/                   # RBAC endpoints (no /api prefix)
/monitoring/             # Internal monitoring
/health                  # Health check (public)
/metrics                 # Prometheus metrics (public)
```

## Creating New Endpoints

### Router Template
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import get_db
from src.core.auth.dependencies import get_current_user
from src.core.models.rbac_models import User

router = APIRouter(
    prefix="/api/v1/your-feature",
    tags=["your-feature"]
)

@router.get("/")
async def list_items(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all items for the current tenant.

    - Automatically filtered by tenant_id from JWT
    - Requires authentication
    """
    # Implementation here
    pass

@router.get("/{item_id}")
async def get_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific item by ID."""
    item = await get_item_by_id(db, item_id, current_user.tenant_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found"
        )
    return item
```

### Register in main.py
```python
# In src/main.py
from src.core.api.your_feature_endpoints import router as your_feature_router

# Add with other routers
app.include_router(your_feature_router)
```

## Authentication Patterns

### Public Endpoints (no auth)
```python
@router.get("/public-info")
async def get_public_info():
    """No authentication required."""
    return {"status": "ok"}
```

### Authenticated Endpoints (default)
```python
@router.get("/protected")
async def get_protected(
    current_user: User = Depends(get_current_user)
):
    """Requires valid JWT token."""
    return {"user_id": current_user.id}
```

### Admin-Only Endpoints
```python
from src.core.auth.dependencies import require_admin

@router.delete("/{item_id}")
async def delete_item(
    item_id: int,
    current_user: User = Depends(require_admin)
):
    """Requires admin role."""
    pass
```

## Response Patterns

### Success Responses
```python
# Single item
return {"id": 1, "name": "Item", "tenant_id": 123}

# List with pagination
return {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
}

# Operation result
return {"success": True, "message": "Item created", "id": 1}
```

### Error Responses
```python
# 400 Bad Request - Client error
raise HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="Invalid input: name is required"
)

# 401 Unauthorized - No/invalid auth
raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token"
)

# 403 Forbidden - Auth OK but no permission
raise HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="You don't have permission to access this resource"
)

# 404 Not Found
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Resource not found"
)

# 422 Validation Error (automatic from Pydantic)
# FastAPI handles this automatically

# 500 Internal Error - Use ErrorDiagnostics
from src.core.api.error_handling import ErrorDiagnostics
try:
    result = await risky_operation()
except Exception as e:
    diagnostics = ErrorDiagnostics.analyze_error(e, "operation_name")
    raise HTTPException(
        status_code=diagnostics["status_code"],
        detail=diagnostics["message"]
    )
```

## Request Validation

### Using Pydantic Schemas
```python
from pydantic import BaseModel, Field

class CreateItemRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    priority: int = Field(default=1, ge=1, le=10)

class ItemResponse(BaseModel):
    id: int
    name: str
    tenant_id: int
    created_at: datetime

    class Config:
        from_attributes = True  # For SQLAlchemy model conversion

@router.post("/", response_model=ItemResponse)
async def create_item(
    request: CreateItemRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new item."""
    pass
```

## Tenant Isolation

### Automatic Filtering
The `TenantMiddleware` automatically sets tenant context. All queries are filtered.

### Manual Tenant Check (when needed)
```python
@router.get("/{item_id}")
async def get_item(item_id: int, current_user: User = Depends(get_current_user)):
    item = await db.get(Item, item_id)

    # Explicit check if not using auto-filter
    if item and item.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Item not found")

    return item
```

## API Documentation

FastAPI auto-generates docs at:
- `/docs` - Swagger UI (interactive)
- `/redoc` - ReDoc (readable)
- `/openapi.json` - OpenAPI spec

### Good Docstrings
```python
@router.post("/execute")
async def execute_workflow(
    workflow_id: int,
    params: ExecuteParams,
    current_user: User = Depends(get_current_user)
):
    """
    Execute a workflow with the given parameters.

    - **workflow_id**: The ID of the workflow to execute
    - **params**: Execution parameters (see schema)

    Returns the execution result with status and outputs.

    Raises:
    - **404**: Workflow not found
    - **400**: Invalid parameters
    - **403**: No permission to execute this workflow
    """
    pass
```
