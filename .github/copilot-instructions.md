# INSTRUCTIONS.md - Development Guidelines

> Dit document bevat alle richtlijnen voor AI-assisted development van het SanskritiSetu platform.

---

## 1. Core Principles

### 1.1 Code Quality Standards
- **Loose Coupling**: Componenten communiceren via interfaces, niet directe dependencies
- **High Cohesion**: Elke module heeft één duidelijke verantwoordelijkheid
- **SOLID Principles**: Strict toepassen op alle code
- **DRY**: Geen code duplicatie, gebruik shared utilities
- **Clean Architecture**: Dependency flow altijd naar binnen (UI → Application → Domain → Infrastructure)

### 1.2 Testing Requirements
```
MINIMUM COVERAGE: 95%

Before ANY code is delivered:
1. Write unit tests FIRST (TDD where possible)
2. Run existing tests - build must NOT break
3. Add integration tests for API endpoints
4. Verify coverage meets 95% threshold
```

### 1.3 Definition of Done
- [ ] Code compiles without errors
- [ ] All existing tests pass
- [ ] New unit tests written (95% coverage)
- [ ] Integration tests for new endpoints
- [ ] Type hints on all functions
- [ ] Docstrings on public methods
- [ ] No linting errors (ruff)
- [ ] Security scan passed

---

## 2. Architecture Rules

### 2.1 Component Structure
```
Every component MUST:
├── Have a single responsibility
├── Expose a clean interface (abstract class/protocol)
├── Be independently testable
├── Have no circular dependencies
└── Be replaceable without affecting other components
```

### 2.2 Dependency Injection
```python
# CORRECT - Dependency Injection
class AgentService:
    def __init__(self, repository: AgentRepository, cache: CacheService):
        self._repository = repository
        self._cache = cache

# WRONG - Hard-coded dependencies
class AgentService:
    def __init__(self):
        self._repository = PostgresAgentRepository()  # ❌
        self._cache = RedisCache()  # ❌
```

### 2.3 Layer Boundaries
```
Presentation Layer (API)
    ↓ (only DTOs/Schemas)
Application Layer (Services)
    ↓ (only domain objects)
Domain Layer (Entities, Value Objects)
    ↓ (only abstractions)
Infrastructure Layer (DB, Cache, External APIs)
```

### 2.4 No Spaghetti Rules
1. **Max 200 lines per file** - Split if larger
2. **Max 20 lines per function** - Extract if larger
3. **Max 3 parameters per function** - Use objects if more
4. **No nested callbacks >2 levels** - Use async/await
5. **No God classes** - Split responsibilities

---

## 3. Testing Protocol

### 3.1 Test Pyramid
```
        /\
       /E2E\        (5%)   - Critical user flows only
      /------\
     /Integr. \     (25%)  - API endpoints, DB queries
    /----------\
   /   Unit     \   (70%)  - All business logic
  /--------------\
```

### 3.2 Test File Structure
```
tests/
├── unit/
│   ├── test_agents/
│   ├── test_mdp/
│   └── test_services/
├── integration/
│   ├── test_api/
│   └── test_database/
└── e2e/
    └── test_flows/
```

### 3.3 Test Commands
```bash
# Run before EVERY commit
pytest tests/unit/ -v --cov=src --cov-fail-under=95

# Run before merge
pytest tests/ -v --cov=src --cov-report=html

# Quick validation
pytest tests/unit/ -x -q  # Stop on first failure
```

### 3.4 Test Naming Convention
```python
def test_<function>_<scenario>_<expected_result>():
    # Example:
    def test_login_with_valid_credentials_returns_jwt():
    def test_login_with_invalid_password_raises_auth_error():
```

---

## 4. Security Standards

### 4.1 Zero-Trust Architecture
```
Every request MUST:
1. Be authenticated (JWT validation)
2. Be authorized (RBAC check)
3. Be tenant-scoped (automatic filter)
4. Be rate-limited
5. Be logged (audit trail)
```

### 4.2 Security Checklist
- [ ] No secrets in code (use env vars)
- [ ] Input validation on ALL endpoints
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (output encoding)
- [ ] CSRF protection on mutations
- [ ] Security headers (OWASP)
- [ ] Encryption at rest (sensitive data)
- [ ] TLS 1.3 in transit

### 4.3 Audit Logging
```python
# Every state-changing operation MUST be logged
await audit_service.log(
    action="user.created",
    actor_id=current_user.id,
    resource_type="user",
    resource_id=new_user.id,
    tenant_id=current_tenant.id,
    changes={"email": new_user.email}
)
```

---

## 5. Performance Standards

### 5.1 Latency Requirements
| Endpoint Type | p50 | p95 | p99 |
|---------------|-----|-----|-----|
| Health check | <10ms | <50ms | <100ms |
| Auth | <100ms | <500ms | <1s |
| CRUD | <200ms | <1s | <2s |
| AI/RAG | <1s | <2s | <5s |

### 5.2 Scalability Rules
- Stateless services (no in-memory state)
- Database connections pooled
- Cache-first for reads
- Async I/O everywhere
- Background jobs for long operations

---

## 6. Git Workflow

### 6.1 Branch Naming
```
feature/<ticket>-<short-description>
bugfix/<ticket>-<short-description>
hotfix/<ticket>-<short-description>
```

### 6.2 Commit Messages
```
<type>(<scope>): <description>

Types: feat, fix, docs, style, refactor, test, chore
Example: feat(agents): add technical agent category
```

### 6.3 PR Checklist
- [ ] Tests pass locally
- [ ] Coverage >= 95%
- [ ] No console.log / print statements
- [ ] Documentation updated
- [ ] Changelog entry added

---

## 7. AI Development Workflow

### 7.1 Before Writing Code
1. Understand the component's single responsibility
2. Define the interface/contract first
3. Write test cases (TDD)
4. Plan the implementation

### 7.2 While Writing Code
1. Follow layer boundaries strictly
2. Use dependency injection
3. Add type hints immediately
4. Keep functions small (<20 lines)

### 7.3 After Writing Code
1. Run `pytest` - all tests must pass
2. Run `ruff check` - no linting errors
3. Check coverage report
4. Verify no breaking changes

### 7.4 Code Review Checklist
```
□ Does it follow Clean Architecture?
□ Is it loosely coupled?
□ Are there unit tests (95%)?
□ Is it secure?
□ Is it performant?
□ Is it documented?
```

---

## 8. Context & Memory Optimization

### 8.1 Session Context
```python
# Store in Redis for session continuity
session_context = {
    "conversation_id": "...",
    "active_files": ["..."],
    "recent_changes": ["..."],
    "current_task": "...",
    "test_status": "passing/failing"
}
```

### 8.2 Project Memory
```
.agent/
├── memory/
│   ├── decisions.md      # Architecture decisions made
│   ├── patterns.md       # Code patterns used
│   ├── issues.md         # Known issues & solutions
│   └── context.json      # Current working context
├── workflows/
│   └── *.md              # Reusable workflows
└── instructions.md       # This file
```

### 8.3 Continuous Learning
- Log all errors with solutions
- Track successful patterns
- Update memory after each session
- Reference previous decisions

---

## 9. Compliance

### 9.1 GDPR Requirements
- Data minimization
- Right to access
- Right to deletion
- Data portability
- Consent tracking
- Privacy by design

### 9.2 EU AI Act Requirements
- Transparency (model logging)
- Explainability (decision tracking)
- Human oversight (audit trails)
- Documentation (ADRs)

---

## 10. File Templates

### New Service
```
Location: src/core/services/<name>_service.py

Template:
class <Name>Service:
    """Service responsible for <responsibility>."""

    def __init__(self, repository: <Name>Repository, cache: CacheService):
        self._repository = repository
        self._cache = cache

    async def get_<resource>(self, id: int, tenant_id: int):
        """Retrieve <resource> with tenant scope."""
        # Implementation
```

### New Agent
```
Location: src/agents/<category>/<name>.py

Template:
class <Name>Agent(BaseAgent):
    """<Name> agent for <responsibility>."""

    def __init__(self, llm: LLMService, tools: List[Tool]):
        super().__init__()
        self.llm = llm
        self.tools = tools

    async def execute(self, query: str):
        """Execute agent logic."""
        # Implementation
```

### New API Route
```
Location: src/core/api/v1/<resource>/router.py

Template:
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/v1/<resource>", tags=["<resource>"])

@router.get("/")
async def list_<resources>(
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user)
):
    """List all <resources> for current tenant."""
    # Implementation
```

### New Test
```
Location: tests/unit/test_<module>/test_<name>.py

Template:
import pytest

@pytest.mark.asyncio
async def test_<function>_<scenario>_<expected>():
    """Test <function> with <scenario> expects <expected>."""
    # Arrange

    # Act

    # Assert
```

---

## 11. Quick Reference

### Development Commands
```bash
# Start development environment
docker-compose -f docker-compose.dev.yml up -d

# Run tests with coverage
pytest tests/ -v --cov=src --cov-fail-under=95

# Check code quality
ruff check src/

# Format code
black src/
isort src/

# Database migrations
alembic -c src/alembic.ini upgrade head

# Create new migration
alembic -c src/alembic.ini revision --autogenerate -m "description"
```

### Important Files
```
Key Architecture Files:
- src/main.py                              # FastAPI entry point
- src/core/database/database.py            # Database configuration
- src/core/middleware/tenant_middleware.py # Multi-tenant isolation
- src/core/security.py                     # Authentication & authorization
- tests/conftest.py                        # Shared test fixtures
- pytest.ini                               # Test configuration
- .pre-commit-config.yaml                  # Code quality hooks
```

### Environment Setup
```bash
# Required environment variables
DATABASE_URL=postgresql+asyncpg://user:password@localhost/db
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=your-secret-key
ENVIRONMENT=development

# For testing
TESTING=1
DATABASE_URL=sqlite+aiosqlite:///file:memdb1?mode=memory
```

---

## 12. Quality Gates

### Before Every Commit
1. ✅ All tests pass: `pytest tests/unit/ -x`
2. ✅ No linting errors: `ruff check src/`
3. ✅ Coverage >= 95%: Check `coverage report`
4. ✅ Type checking: `mypy src/`

### Before Merging PR
1. ✅ All tests pass (unit + integration): `pytest tests/`
2. ✅ No security vulnerabilities: Bandit scan
3. ✅ Coverage report generated and reviewed
4. ✅ Changelog entry added
5. ✅ Documentation updated

---

## 13. Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'src'` | Set `PYTHONPATH=src` or run from project root |
| Test DB connection fails | Check `DATABASE_URL` env var, ensure SQLite or test DB exists |
| Tenant filter not working | Verify middleware is registered in `src/main.py` |
| Cache miss on startup | Seed Redis with `python scripts/seed_cache.py` |
| JWT token expired | Issue new token via `/api/v1/auth/login` |
| Enum mismatch errors | Import ALL enums from `src/core/types.py` only |

---

**Last Updated**: January 2026
**Version**: 1.0
