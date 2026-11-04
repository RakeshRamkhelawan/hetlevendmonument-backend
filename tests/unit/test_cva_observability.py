"""Observability tests for CVA service.

Ref: CVA Audit Phase 5 - Observability
"""

import ast
from pathlib import Path

import pytest


class TestStructuredLogging:
    """Logger calls should use structured extra dict, not f-strings."""

    def test_no_fstring_in_logger_calls(self):
        """CVAService should not use f-strings in logger calls."""
        source_path = Path("src/core/services/cva_service.py")
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        fstring_logger_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in (
                    "info",
                    "warning",
                    "error",
                    "exception",
                    "debug",
                ):
                    if isinstance(func.value, ast.Name) and func.value.id == "logger":
                        for arg in node.args:
                            if isinstance(arg, ast.JoinedStr):
                                fstring_logger_calls.append(node.lineno)

        assert fstring_logger_calls == [], (
            f"Found f-string logger calls at lines: {fstring_logger_calls}. "
            "Use logger.info('message', extra={...}) for structured logging."
        )

    def test_structured_logging_imports(self):
        """CVAService should import/use structured logging utilities."""
        source_path = Path("src/core/services/cva_service.py")
        source = source_path.read_text(encoding="utf-8")

        # Check for structured logging patterns
        has_structured_logging = "extra=" in source

        assert (
            has_structured_logging
        ), "Expected structured logging with extra= payloads in CVA service logs"
