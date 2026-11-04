"""
Test that pyright baseline file exists.
Phase B1.3: Baseline generation verification.
"""

from pathlib import Path
import json


def test_pyright_baseline_exists():
    """pyright-baseline.json must exist after generation."""
    baseline_path = Path("pyright-baseline.json")
    assert baseline_path.exists(), "pyright-baseline.json must exist"


def test_pyright_baseline_is_valid_json():
    """Baseline must be valid JSON mapping file paths to error counts."""
    baseline_path = Path("pyright-baseline.json")
    with open(baseline_path, encoding="utf-8") as f:
        baseline = json.load(f)
    assert isinstance(baseline, dict), "Baseline must be a dict"
    assert len(baseline) > 0, "Baseline must have at least one file"
