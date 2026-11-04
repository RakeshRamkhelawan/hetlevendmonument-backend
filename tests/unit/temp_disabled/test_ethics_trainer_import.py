"""TDD tests for A2.14: ethics_classification_trainer.py lazy import."""

import os
import subprocess
import sys
import tempfile


def test_ethics_trainer_imports_cleanly() -> None:
    """Module should import without creating directories or crashing."""
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

sys.path.insert(0, {os.getcwd()!r})
os.chdir({tmpdir!r})

sys.modules.pop("src.core.agents.ethics_classification_trainer", None)

import src.core.agents.ethics_classification_trainer as et

# Check that ethics_trainer was NOT instantiated at import time
has_instance = "ethics_trainer" in et.__dict__
print(f"has_instance={{has_instance}}")
if has_instance:
    sys.exit(1)

# Check that directories were NOT created at import time
data_dir = os.path.join({tmpdir!r}, "data", "ethics_training")
has_data = os.path.exists(data_dir)
print(f"has_data={{has_data}}")
if has_data:
    sys.exit(1)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"Lazy check failed: {result.stdout} {result.stderr}"


def test_ethics_trainer_factory_works() -> None:
    """Factory should instantiate correctly when called."""
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

sys.path.insert(0, {os.getcwd()!r})
os.chdir({tmpdir!r})

sys.modules.pop("src.core.agents.ethics_classification_trainer", None)

from src.core.agents.ethics_classification_trainer import get_ethics_trainer

trainer = get_ethics_trainer()
print(f"trainer_type={{type(trainer).__name__}}")
print(f"has_model_configs={{bool(trainer.model_configs)}}")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"Factory check failed: {result.stdout} {result.stderr}"
        assert "trainer_type=EthicsClassificationTrainer" in result.stdout
