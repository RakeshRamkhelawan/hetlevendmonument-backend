"""TDD tests for A2.11: cva_file_manager.py lazy import."""

import os
import subprocess
import sys
import tempfile


def test_cva_file_manager_imports_cleanly() -> None:
    """Module should import without creating directories at import time."""
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

sys.modules.pop("src.core.agents.cva_file_manager", None)

import src.core.agents.cva_file_manager as cfm

# Check that directories were NOT created at import time
temp_dir = os.path.join({tmpdir!r}, "temp")
downloads_dir = os.path.join({tmpdir!r}, "downloads")
has_temp = os.path.exists(temp_dir)
has_downloads = os.path.exists(downloads_dir)
print(f"has_temp={{has_temp}} has_downloads={{has_downloads}}")
if has_temp or has_downloads:
    sys.exit(1)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"Lazy check failed: {result.stdout} {result.stderr}"
