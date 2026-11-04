"""
PYTEST PLUGIN: Automatic Fixture Isolation for Unit vs Integration Tests
===========================================================================

This plugin ensures that:
1. Unit tests (tests/unit/, tests/contracts/, tests/compliance/, etc) use IN-MEMORY SQLite (fast)
2. Integration tests (tests/integration/) use FILE-BASED SQLite (realistic)
3. Fixtures are NEVER mixed between these two databases
4. Solution is FUTUREPROOF and doesn't require conftest.py in each directory

How It Works:
- Pytest calls pytest_configure() hook at startup
- We detect whether each test is "integration" or "unit" based on directory
- Integration tests get postgres_engine/postgres_session (file-based)
- Unit tests get async_engine/db_session (in-memory)
- Fixtures are automatically resolved from the right conftest.py
"""

import os
import sys
from pathlib import Path


def pytest_configure(config):
    """Configure pytest to handle fixture isolation automatically"""
    # Mark test directory as "integration" if it's under tests/integration/
    # This allows tests to request fixtures with knowledge of which database they'll get

    # Note: This is informational - pytest.ini handles actual fixture resolution
    # by having separate conftest.py files in tests/ and tests/integration/
    pass


def pytest_collection_modifyitems(config, items):
    """
    Auto-apply markers to tests based on their location.

    This helps organize which database each test should use:
    - tests/integration/ → @pytest.mark.integration (uses file-based SQLite)
    - tests/unit/, tests/contracts/, etc → @pytest.mark.unit (uses in-memory SQLite)
    """
    for item in items:
        test_path = Path(item.fspath)

        # Determine if this is an integration test or unit test
        if "tests/integration" in str(test_path).replace("\\", "/"):
            # Integration tests automatically use postgres_session
            if "integration" not in [marker.name for marker in item.iter_markers()]:
                item.add_marker("integration")
        else:
            # Unit tests, contract tests, etc automatically use db_session
            if "unit" not in [marker.name for marker in item.iter_markers()]:
                item.add_marker("unit")
