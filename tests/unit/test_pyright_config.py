"""
Test that pyright configuration exists and is valid.
Phase B1.1: RED-GREEN-REFACTOR for type checking foundation.
"""

import json
from pathlib import Path


def test_pyright_config_exists():
    """pyrightconfig.json must exist in project root."""
    config_path = Path("pyrightconfig.json")
    assert config_path.exists(), "pyrightconfig.json must exist in project root"


def test_pyright_config_is_valid_json():
    """pyrightconfig.json must contain valid JSON with required keys."""
    config_path = Path("pyrightconfig.json")
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    assert "include" in config, "Must have 'include' key"
    assert "baselineFile" in config, "Must have 'baselineFile' key"
