#!/usr/bin/env python3
"""
Unicode utility functions for cross-platform compatibility
Implements StatusIcons and safe printing from UNICODE_BEST_PRACTICES.md
"""

import logging
import sys
from typing import Optional


class StatusIcons:
    """Cross-platform compatible status indicators"""

    def __init__(self, use_unicode: bool | None = None) -> None:
        if use_unicode is None:
            self.use_unicode = self._detect_unicode_support()
        else:
            self.use_unicode = use_unicode

    def _detect_unicode_support(self) -> bool:
        """Detect if current environment supports Unicode"""
        try:
            # Test if we can encode Unicode characters
            test_char = "\u2705"
            encoding = sys.stdout.encoding or "utf-8"
            test_char.encode(encoding)
            return True
        except (UnicodeEncodeError, LookupError, AttributeError):
            return False

    @property
    def success(self) -> str:
        return "\u2705" if self.use_unicode else "[OK]"

    @property
    def warning(self) -> str:
        return "\u26a0\ufe0f" if self.use_unicode else "[WARN]"

    @property
    def error(self) -> str:
        return "\u274c" if self.use_unicode else "[ERROR]"

    @property
    def info(self) -> str:
        return "\u2139\ufe0f" if self.use_unicode else "[INFO]"

    @property
    def rocket(self) -> str:
        return "\U0001f680" if self.use_unicode else "[LAUNCH]"

    @property
    def check(self) -> str:
        return "\u2713" if self.use_unicode else "[PASS]"


def safe_print(message: str, fallback_encoding: str = "ascii") -> None:
    """Safely print messages with Unicode fallback"""
    try:
        print(message)
    except UnicodeEncodeError:
        # Remove or replace problematic characters
        safe_message = message.encode(fallback_encoding, errors="replace").decode(fallback_encoding)
        print(f"[UNICODE_SAFE] {safe_message}")


def safe_log_info(message: str, logger: logging.Logger | None = None) -> None:
    """Log message with Unicode safety"""
    if logger is None:
        logger = logging.getLogger()

    try:
        logger.info(message)
    except UnicodeEncodeError:
        safe_message = message.encode("ascii", errors="replace").decode("ascii")
        logger.info(f"[UNICODE_SAFE] {safe_message}")


def strip_unicode(text: str) -> str:
    """Remove Unicode characters for Windows compatibility"""
    import re

    # Remove Unicode symbols and emoji
    return re.sub(r"[^\x00-\x7F]+", "", text)


# Global instance for easy use
icons = StatusIcons()
