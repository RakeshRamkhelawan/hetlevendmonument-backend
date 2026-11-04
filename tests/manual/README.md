# Manual Test Scripts

This directory contains **manual test scripts** used during development and debugging of the SanskritiSetu platform. These are standalone scripts (not pytest tests) that verify specific functionality.

## 📁 Directory Structure

```
tests/manual/
├── Auth & Login Tests (10+ files)
│   ├── test_auth_*.py          # Authentication flow tests
│   ├── test_login_*.py          # Login endpoint tests
│   └── test_bearer_debug.py     # JWT bearer token debugging
│
├── API & Backend Tests
│   ├── test_backend_*.py        # Backend API functionality
│   ├── test_chat_endpoint.py    # Chat/AI endpoint tests
│   └── test_me_*.py             # User profile endpoint tests
│
├── Frontend Tests
│   ├── test_frontend*.py        # Frontend integration tests
│   ├── test_docker_frontend.py  # Docker-based frontend tests
│   └── test_react_flow.py       # React application flow tests
│
├── VIBE Tests
│   ├── test_vibe_95percent.py   # VIBE 95% coverage test
│   ├── test_vibe_autonomous_org.py # Autonomous organization test
│   └── test_vibe_complete.py    # Complete VIBE workflow test
│
├── Workflow & Integration Tests
│   ├── test_workflow_generation_logging.py
│   └── complete_ui_test.py      # Full UI integration test
│
└── Connectivity & Infrastructure
    ├── test_all_vite_ips.py     # Vite dev server IP testing
    ├── test_basic_connectivity.py
    ├── test_db_connection.py    # Database connection verification
    ├── test_ports.py            # Port availability checks
    └── test_bcrypt.py           # Password hashing verification
```

## 🎯 Purpose

These scripts serve multiple purposes:

1. **Development Debugging**: Quick verification during feature development
2. **Integration Testing**: End-to-end flows that span multiple components
3. **Environment Validation**: Verify deployment configurations
4. **Troubleshooting**: Isolate issues in specific subsystems

## 🔧 Usage

Most scripts can be run standalone:

```powershell
# Run a specific manual test
python tests/manual/test_auth_complete.py

# From root directory
python tests/manual/test_backend_api.py
```

Some scripts may require environment variables:

```powershell
$env:DATABASE_URL = "postgresql://..."
$env:JWT_SECRET = "your-secret"
python tests/manual/test_login_endpoint.py
```

## ⚠️ Important Notes

- **Not Pytest Tests**: These are NOT part of the automated pytest suite
- **Manual Execution**: Designed for manual, ad-hoc testing
- **Development Only**: Should not be used in production environments
- **Path Independence**: Scripts use `Path(__file__).parent.parent` for imports

## 🔄 Migration History

These scripts were **moved to `tests/manual/` on 2026-02-05** (Phase 5 of root directory cleanup).

**Original Location**: Project root (`./test_*.py`)
**Reason for Move**: Improve root directory organization for commercial readiness
**Git Commit**: `89c3208c5` - Phase 5: Organize test scripts and analysis tools

## 📝 Maintenance

When adding new manual test scripts:

1. ✅ Place in `tests/manual/`
2. ✅ Use descriptive naming: `test_<component>_<scenario>.py`
3. ✅ Include docstring explaining purpose
4. ✅ Use `Path(__file__).parent.parent` for imports
5. ✅ Add to `.gitignore` if generating output files

## 🔗 Related

- **Automated Tests**: See `tests/unit/`, `tests/integration/`, `tests/e2e/`
- **Analysis Tools**: See `scripts/analysis/` for test result analyzers
- **Debug Scripts**: See `scripts/debug/` for debugging utilities

---

**Last Updated**: 2026-02-05
**Total Scripts**: 47
**Maintained By**: SanskritiSetu Development Team
