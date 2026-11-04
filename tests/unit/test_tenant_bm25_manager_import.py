"""TDD tests for A2.13: tenant_bm25_manager.py lazy import."""

import os
import subprocess
import sys
import tempfile


def test_tenant_bm25_manager_imports_cleanly() -> None:
    """Module should import without creating index directory at import time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {
            **os.environ,
            "TESTING": "1",
            "DATABASE_URL": "sqlite+aiosqlite:///test.db",
            "REDIS_URL": "redis://localhost:6379/0",
            "SECRET_KEY": "test-secret-key-32-chars-long!!!!!",
            "JWT_SECRET_KEY": "test-jwt-secret-key-32-chars-long!",
        }
        code = f"""
import os
import sys

# Add project root to path so 'src' is importable
sys.path.insert(0, {os.getcwd()!r})
os.chdir({tmpdir!r})

sys.modules.pop("src.core.search.tenant_bm25_manager", None)

import src.core.search.tenant_bm25_manager as tbm

# Check that index directory was NOT created at import time
index_dir = os.path.join({tmpdir!r}, "data", "bm25_indexes")
has_index = os.path.exists(index_dir)
print(f"has_index={{has_index}}")
if has_index:
    sys.exit(1)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"Lazy check failed: {result.stdout} {result.stderr}"
