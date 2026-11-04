"""Test that logging handles Unicode characters on all platforms."""

from unittest.mock import patch

import pytest


def test_logging_handles_unicode_on_windows():
    """Loguru should not raise UnicodeEncodeError with emoji/special chars on Windows."""
    with patch("os.name", "nt"), patch.dict("os.environ", {"ENVIRONMENT": "production"}):
        import importlib

        from src.core.observability import logging as log_module

        importlib.reload(log_module)
        log_module.configure_logging()

        from loguru import logger

        try:
            logger.info("Test with arrow: → and checkmark: ✓")
        except UnicodeEncodeError:
            pytest.fail("UnicodeEncodeError raised — logging not Unicode-safe")
