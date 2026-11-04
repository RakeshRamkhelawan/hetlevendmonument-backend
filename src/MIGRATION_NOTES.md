# Migration Notes

## Extraction Date

$(date +"%Y-%m-%d %H:%M:%S")

## Files Copied

- Core directory: 309 Python files
- Agent directories: 4 directories (34 files)
- Supporting files: main.py, config.py, requirements.txt, alembic/

## Changes Made

### 1. Hardcoded Paths

- Fixed `core/tool_broker/mcp_client.py`
  - Replaced hardcoded Windows path with `Path(__file__).parent.parent.parent`

### 2. Package References

- Updated `config.py` (if present)
- Updated `setup.py` (if present)
- Changed "stichting" → "sanskriti" where needed

### 3. Directory Structure

Maintained exact directory structure to preserve relative imports.

## Dependencies

### Required Agent Directories

The following agent directories are REQUIRED by `core/collaboration/task_distributor.py`:

- agents/knowledge_agent/
- agents/sentiment_agent/
- agents/diagnostics_agent/
- agents/translation_agent/

### Circular Dependency

There is 1 circular dependency:

```text
core/auth/rbac.py ↔ core/api/auth_endpoints.py
```text

This is handled with lazy imports but should be refactored.

## Testing Checklist

- [ ] Import all core modules successfully
- [ ] Start main.py without errors
- [ ] Database connection works
- [ ] API endpoints respond
- [ ] Agent coordination functions
- [ ] Run test suite

## Next Steps

1. Update .env file with correct settings
2. Run database migrations: `alembic upgrade head`
3. Test import statements: `python -c "from core.auth import auth_service"`
4. Start server: `python main.py`
5. Run tests: `pytest tests/`
6. Review and fix any issues

## Known Issues to Address

1. Resolve circular dependency between rbac.py and auth_endpoints.py
2. Review all configuration paths
3. Update any remaining hardcoded references
4. Add comprehensive tests for extracted components
