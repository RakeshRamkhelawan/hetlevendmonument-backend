"""Tests for scripts/run_mypy_audit.py's parse_errors() line-matching regex.

In-process only (no subprocess) so these stay fast and unaffected by the
subprocess-timeout issue that quarantined tests/unit/temp_disabled/test_mypy_audit.py.

Loaded via spec_from_file_location rather than `from scripts.run_mypy_audit import ...`:
tests/unit/scripts/__init__.py exists with no parent tests/unit/__init__.py, so under
pytest's --import-mode=importlib, collecting that directory registers sys.modules["scripts"]
as tests/unit/scripts -- permanently shadowing the real top-level scripts/ package for the
rest of the test session, regardless of where this file lives.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "_run_mypy_audit_under_test",
    Path(__file__).resolve().parent.parent.parent / "scripts" / "run_mypy_audit.py",
)
assert _SPEC and _SPEC.loader
_run_mypy_audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_run_mypy_audit)
parse_errors = _run_mypy_audit.parse_errors


@pytest.mark.unit
class TestParseErrors:
    """Verify parse_errors() counts every mypy error line, wrapped or not."""

    def test_handles_column_numbers(self) -> None:
        """file:line:col: error: msg format is counted per file."""
        lines = [
            "src/foo/bar.py:42:7: error: Cannot find something",
            "src/foo/bar.py:43:1: error: Another error",
            "src/baz/qux.py:10:15: error: Third error",
            "Some other output line that doesn't match",
        ]
        counts = parse_errors(lines)
        assert counts == {"src/foo/bar.py": 2, "src/baz/qux.py": 1}

    def test_handles_wrapped_message_with_no_text_on_error_line(self) -> None:
        """mypy's pretty-printer sometimes wraps a long message so nothing
        follows "error:" on that physical line (real repro from
        src/core/api/v1/analytics_ingest/events_router.py:137/199). Without
        this, the line silently fails to match and the error is dropped.
        """
        lines = [
            "src/foo/events_router.py:137:28: error:",
            '"dict[str, Any]" has no attribute "id"  [attr-defined]',
            "src/foo/events_router.py:199:28: error:",
            '"dict[str, Any]" has no attribute "id"  [attr-defined]',
        ]
        counts = parse_errors(lines)
        assert counts == {"src/foo/events_router.py": 2}

    def test_handles_mixed_wrapped_and_inline_messages(self) -> None:
        """A file with some wrapped and some inline error lines is still
        counted correctly for both.
        """
        lines = [
            "src/foo/dsar_service.py:332:41: error: Argument 1 to",
            '"ConversationMemory" has incompatible type "AsyncRedisClient"',
            "src/foo/events_router.py:137:28: error:",
            '"dict[str, Any]" has no attribute "id"  [attr-defined]',
        ]
        counts = parse_errors(lines)
        assert counts == {"src/foo/dsar_service.py": 1, "src/foo/events_router.py": 1}
