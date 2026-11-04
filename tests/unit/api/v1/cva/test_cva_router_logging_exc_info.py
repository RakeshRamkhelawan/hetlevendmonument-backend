"""BE-003: chat_router.py foutpaden MOETEN exc_info=True gebruiken in logger.error() calls.

Architecture test: controleert dat alle error-log aanroepen in chat_router.py
die een exception loggen, ook exc_info=True bevatten.
"""

import re
from pathlib import Path


class TestCVARouterLoggingExcInfo:
    """chat_router.py MOET exc_info=True gebruiken in alle logger.error() exception-log calls."""

    def _get_logger_error_calls_without_exc_info(self) -> list[tuple[int, str]]:
        """Geeft alle logger.error() regels terug zonder exc_info (in exception-blokken)."""
        source = (
            Path(__file__).resolve().parents[5] / "src/core/api/v1/cva/chat_router.py"
        ).read_text(encoding="utf-8")
        lines = source.splitlines()
        missing: list[tuple[int, str]] = []
        in_except = False
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("except "):
                in_except = True
            elif in_except and (stripped.startswith("try:") or stripped == ""):
                pass
            elif in_except and not stripped.startswith("except ") and not stripped.startswith("#"):
                if stripped.startswith("logger.error(") and "exc_info" not in stripped:
                    # Only flag single-line logger.error calls (multi-line need separate check)
                    if stripped.endswith(")"):
                        missing.append((i, stripped))
        return missing

    def test_logger_error_in_except_blocks_has_exc_info(self):
        """Alle logger.error() calls in except-blokken MOETEN exc_info=True hebben (BE-003)."""
        source = (
            Path(__file__).resolve().parents[5] / "src/core/api/v1/cva/chat_router.py"
        ).read_text(encoding="utf-8")

        # Find all logger.error() calls (single-line) and verify they have exc_info
        # Exclude logger.exception() -- those have exc_info implicitly
        problem_lines: list[tuple[int, str]] = []
        lines = source.splitlines()
        in_except = False
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if re.match(r"except\s+\w", stripped):
                in_except = True
            elif stripped.startswith("try:"):
                in_except = False
            if in_except and "logger.error(" in stripped and "exc_info" not in stripped:
                # Multi-line calls: scan up to 8 continuation lines for exc_info
                multiline_ctx = " ".join(line.strip() for line in lines[i - 1 : i + 8])
                if "exc_info" not in multiline_ctx:
                    problem_lines.append((i, stripped[:80]))

        assert not problem_lines, (
            f"chat_router.py heeft {len(problem_lines)} logger.error() call(s) zonder exc_info=True:\n"
            + "\n".join(f"  lijn {ln}: {txt}" for ln, txt in problem_lines)
            + "\nBE-003: voeg exc_info=True toe aan alle logger.error() calls in except-blokken."
        )

    def test_llm_timeout_error_handler_logs_with_exc_info(self):
        """LLMTimeoutError handler MOET exc_info=True loggen (BE-003)."""
        source = (
            Path(__file__).resolve().parents[5] / "src/core/api/v1/cva/chat_router.py"
        ).read_text(encoding="utf-8")
        lines = source.splitlines()

        in_llm_timeout = False
        has_exc_info = False
        for j, line in enumerate(lines):
            stripped = line.strip()
            if "except LLMTimeoutError" in stripped:
                in_llm_timeout = True
            elif in_llm_timeout:
                if stripped.startswith("except ") or stripped.startswith("finally"):
                    break
                if "logger.error(" in stripped:
                    # Handle multi-line calls: scan this line + next 8 lines for exc_info
                    ctx = " ".join(line.strip() for line in lines[j : j + 8])
                    if "exc_info" in ctx:
                        has_exc_info = True
                    break

        assert (
            has_exc_info
        ), "LLMTimeoutError except-block in chat_router.py logt NIET met exc_info=True (BE-003)."
