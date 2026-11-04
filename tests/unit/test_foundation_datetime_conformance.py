"""Test suite voor BE-UTL-050: Foundation Datetime Guardrail Conformance.

Verifieert dat alle tijdsberekeningen in foundation modules uitsluitend
gebruikmaken van utc_now() conform de project guardrails (CLAUDE.md / AGENTS.md).
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import sys
import pytest

sys.path.insert(0, ".")
from src.core.shared.datetime_utils import utc_now


def test_utc_now_guarantees_timezone_aware_utc():
    """Valideer dat utc_now() altijd een timezone-aware datetime in UTC oplevert."""
    now = utc_now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
    assert now.tzinfo == timezone.utc


def test_no_datetime_now_in_foundation_modules():
    """Valideer statisch via AST dat datetime.now() of datetime.utcnow() niet voorkomt in foundation API bestanden."""
    foundation_dir = Path("src/core/api/v1/foundation")
    py_files = list(foundation_dir.glob("**/*.py"))
    assert len(py_files) > 0

    violations: list[str] = []

    for file_path in py_files:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Detecteer datetime.now(...) of datetime.utcnow(...)
                if isinstance(func, ast.Attribute) and func.attr in ("now", "utcnow"):
                    if isinstance(func.value, ast.Name) and func.value.id == "datetime":
                        violations.append(
                            f"{file_path.name}:{node.lineno} aanroep van datetime.{func.attr}()"
                        )

    assert not violations, "Onverwachte datetime.now/utcnow aanroepen gevonden:\n" + "\n".join(
        violations
    )


if __name__ == "__main__":
    test_utc_now_guarantees_timezone_aware_utc()
    print("test_utc_now_guarantees_timezone_aware_utc PASSED")
    test_no_datetime_now_in_foundation_modules()
    print("test_no_datetime_now_in_foundation_modules PASSED")
