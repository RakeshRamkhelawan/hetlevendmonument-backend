---
description: Architecture reference for SanskritiSetu codebase
applyTo: 'src/**'
---

# Architecture Instructions

## Project Structure

```
src/
├── main.py                    # FastAPI app entry point
├── core/
│   ├── api/                   # 40+ endpoint routers
│   │   ├── auth_endpoints.py
│   │   ├── workflow_endpoints.py
│   │   └── ...
│   ├── database/
│   │   ├── database.py        # Base, engine, session factory
│   │   ├── models.py          # DEPRECATED - use domain models
│   │   └── tenant_query_filter.py
│   ├── middleware/
│   │   ├── tenant_middleware.py   # Multi-tenant isolation
│   │   ├── tenant_context.py      # ContextVar storage
│   │   ├── rate_limiter.py
│   │   └── security_headers.py
│   ├── models/
│   │   └── rbac_models.py     # User, Role, Tenant
│   ├── agents/
│   │   └── models.py          # RegisteredAgent, Agent
│   ├── types.py               # SINGLE SOURCE for all enums
│   └── services/              # Business logic layer
```

## Critical Design Decisions

### 1. Single Source of Truth for Types
```python
# ALWAYS import from src.core.types
from src.core.types import (
    AgentType,      # CVA, ORCHESTRATOR, ETHICS, SPECIALIST...
    TriggerType,    # MANUAL, SCHEDULED, AUTO, EVENT_DRIVEN...
    WorkflowState,  # PENDING, RUNNING, SUCCEEDED, FAILED...
    TaskStatus,     # PENDING, IN_PROGRESS, COMPLETED...
    TaskPriority,   # LOW, MEDIUM, HIGH, CRITICAL
    AgentStatus,    # ACTIVE, INACTIVE, TRAINING, ARCHIVED
    IsolationLevel, # MOCK, PROCESS, CONTAINER, DOCKER, VM
)

# NEVER redefine enums elsewhere - causes type mismatches
```

### 2. Multi-Tenant Architecture
Every database model with tenant data MUST have:
```python
class MyModel(Base):
    __tablename__ = "my_models"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    # ... other fields
```

The `TenantMiddleware` automatically:
1. Extracts `tenant_id` from JWT token
2. Sets `ContextVar` for current request
3. Auto-filters all queries via `tenant_query_filter.py`

### 3. Import Conventions
```python
# CORRECT - Use src. prefix
from src.core.database.database import Base, get_db
from src.core.models.rbac_models import User, Role, Tenant
from src.core.agents.models import RegisteredAgent
from src.core.types import AgentType, WorkflowState

# WRONG - Old paths (deprecated, will show warnings)
from core.database.models import User  # DeprecationWarning!
```

### 4. Database Model Locations
| Model | Location | Purpose |
|-------|----------|---------|
| User, Role, Tenant | `src/core/models/rbac_models.py` | Auth & RBAC |
| Agent, RegisteredAgent | `src/core/agents/models.py` | AI agents |
| CVAConversation | `src/core/conversations/models.py` | Chat history |
| FeatureFlag | `src/core/feature_flags/models.py` | Feature toggles |
| KnowledgeEntry | `src/core/knowledge/models.py` | Knowledge base |
| AuditLog | `src/core/governance/models.py` | Audit trail |

## Adding New Components

### New API Endpoint
1. Create `src/core/api/your_endpoints.py`:
```python
from fastapi import APIRouter, Depends
from src.core.database.database import get_db

router = APIRouter(prefix="/api/v1/your-feature", tags=["your-feature"])

@router.get("/")
async def list_items(db = Depends(get_db)):
    # Implementation
    pass
```

2. Register in `src/main.py`:
```python
from src.core.api.your_endpoints import router as your_router
app.include_router(your_router)
```

3. Add tests in `tests/unit/test_your_endpoints.py`

### New Database Model
1. Create in appropriate domain module
2. Import `Base` from `src.core.database.database`
3. Include `tenant_id` if tenant-scoped
4. Create migration: `alembic revision --autogenerate -m "Add your_model"`
5. Apply: `alembic upgrade head`

### New Enum/Type
1. Add ONLY to `src/core/types.py`
2. Import from there in all other files
3. Never create local enum definitions

## Service Layer Pattern
```python
# src/core/services/your_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.models.rbac_models import User

class YourService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_item(self, data: dict, user: User) -> Item:
        # Business logic here
        item = Item(**data, created_by=user.id, tenant_id=user.tenant_id)
        self.db.add(item)
        await self.db.flush()
        return item
```

## Error Handling Pattern
```python
from fastapi import HTTPException, status

# Use specific HTTP status codes
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Resource not found"
)

# For validation errors
raise HTTPException(
    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    detail={"field": "name", "error": "Name is required"}
)
```
