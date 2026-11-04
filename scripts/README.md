# Scripts Directory

This directory contains operational scripts organized by category after **Phase 7 consolidation** (Feb 2026).

## 📁 Structure

```text
scripts/
├── analysis/           # Analysis & reporting tools
├── tests/             # Test runners (from Phase 8)
├── utilities/         # Utility scripts (from Phase 8)
├── *.py               # Operational scripts (database, seed, orchestrator, user management)
└── README.md          # This file
```

## 🚀 How to Run Scripts

**IMPORTANT**: Always run scripts from the **project root**, not from within the `scripts/` directory.

### ✅ Correct Usage

```bash
# From project root
cd /path/to/SanskritiSetu.org

# Run any script
python scripts/seed_demo.py
python scripts/orchestrator_cli.py
python scripts/rebuild_database_dual_tenant.py
```

### ❌ Incorrect Usage

```bash
# DON'T do this - will cause ImportError
cd scripts
python seed_demo.py  # ❌ ImportError: No module named 'src'
```

### Why?

Scripts import from the `src/` module which is located at project root level:

```python
from src.core.database.database import db_manager  # Expects 'src' at root
```

Running from project root ensures Python can find the `src/` package.

## 📦 Script Categories

### Database & Seeding
- `seed_demo.py` - Seed demo data
- `seed_demo_agents.py` - Seed agent data
- `seed_workflow.py` - Seed workflow data
- `rebuild_database_dual_tenant.py` - Rebuild database with dual-tenant setup
- `fix_db_schema.py` - Fix database schema issues
- `create_all_missing_tables.py` - Create missing database tables

### Orchestrators
- `copilot_orchestrator_cli.py` - Copilot orchestrator CLI
- `orchestrator_cli.py` - Main orchestrator CLI
- `orchestrator_demo.py` - Orchestrator demo

### User Management
- `create_admin_prod.py` - Create admin user (production)
- `create_sqlite_user.py` - Create SQLite test user
- `create_vibe_test_user.py` - Create vibe test user
- `create_vibe_user.py` - Create vibe user
- `create_account_lockouts.py` - Create test account lockouts
- `quick_create_user.py` - Quick user creation utility
- `setup_admin.py` - Setup admin account

### Test Runners (Phase 8)

See `tests/` subdirectory for test execution scripts.

### Phase 7 Compose E2E

- `run_phase7_compose.ps1` - Runs the full Phase 7 compose-backed learning validation against `.env.test`

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_phase7_compose.ps1
```

Config-only check:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_phase7_compose.ps1 -ConfigOnly
```

VS Code task:

```text
Phase 7: Compose E2E
```

### Utilities (Phase 8)
See `utilities/` subdirectory for utility scripts.

### Display & Analysis
- `display_95_percent_workflow.py` - Display 95% workflow coverage
- `display_vibe_results.py` - Display vibe coding results
- `generate_user_stories.py` - Generate user stories
- `list_routes.py` - List API routes
- `migrate_imports.py` - Migrate import statements
- `scan_docker_imports.py` - Scan Docker imports

### Coverage Tools
- `coverage_phase2.py` - Phase 2 coverage analysis
- `coverage_phase3.py` - Phase 3 coverage analysis
- `get_coverage.py` - Get coverage report
- `monitor_coverage_baseline.py` - Monitor coverage baseline
- `fast_coverage_batch.py` - Fast batch coverage
- `run_module_coverage.py` - Run module coverage
- `run_test_batches.py` - Run test batches
- `run_individual_tests.py` - Run individual tests
- `run_jwt_tests.py` - Run JWT tests
- `run-tests.py` - Main test runner
- `e2e_test_all_features.py` - E2E feature tests

### Manual Tests
- `visual_e2e_test.py` - Visual E2E testing
- `simple_login_test.py` - Simple login test
- `tests_manual_unhappy.py` - Manual unhappy path tests
- `tests_manual_graph_unhappy.py` - Manual graph unhappy tests
- `tests_manual_websocket_unhappy.py` - Manual WebSocket unhappy tests

### Other
- `read_log.py` - Read and parse logs

## 🛠️ Troubleshooting

### "ModuleNotFoundError: No module named 'src'"

**Cause**: You're running the script from within the `scripts/` directory.

**Solution**: Navigate to project root and run:
```bash
cd ..  # Go back to project root
python scripts/your_script.py
```

### "ImportError: Cannot import name 'X' from 'src.Y'"

**Cause**: Missing dependencies or database not initialized.

**Solution**:
1. Ensure virtual environment is activated
2. Install dependencies: `pip install -r requirements.txt`
3. Initialize database: `python init_dev_db.py`

## 📚 Related Directories

- `/debug-scripts/` - Debug and verification scripts
- `/deployment-scripts/` - Deployment automation (Phase 8)
- `/test-outputs/` - Test result outputs (Phase 2)
- `/logs/` - Log files (Phase 1)

---

**Last Updated**: 2026-02-05 (Phase 7 Consolidation)
**Migration**: Part of root directory cleanup (Phase 0-7)
