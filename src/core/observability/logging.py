"""
Structured logging configuration with Loguru.
Handles Unicode encoding on Windows and avoids circular imports.
"""

import io
import os
import sys
from typing import Any

from loguru import logger


def configure_logging() -> None:
    """
    Configure Loguru to output structured JSON logs with tenant context.
    Forces UTF-8 encoding on Windows to prevent UnicodeEncodeError.
    """
    # Remove default handler
    logger.remove()

    is_windows = os.name == "nt"

    if is_windows:
        # Keep pytest/stdout capture stable; avoid wrapping stdout.buffer, which can
        # break capture teardown when wrapper lifetimes diverge.
        if isinstance(sys.stdout, io.TextIOWrapper):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                # Fallback to existing stream config when reconfigure is unavailable.
                pass

        logger.add(
            sys.stdout,
            format="[{time:YYYY-MM-DD HH:mm:ss}] {level}: {message}",
            level="INFO",
            filter=tenant_context_filter,
        )
    else:
        # Unix/production: JSON structured logging
        logger.add(
            sys.stdout,
            format="{message}",
            serialize=True,
            level="INFO",
            filter=tenant_context_filter,
        )


def tenant_context_filter(record: Any) -> bool:  # TODO(TYPE): replace Any with concrete type
    """
    Inject tenant_id into the log record extra dict.
    This makes it available in the JSON output.

    Uses lazy import to prevent circular dependency with container.
    Return type corrected from None to bool (Loguru filter protocol).
    """
    try:
        from src.core.middleware.tenant_context import get_tenant_id

        tenant_id = get_tenant_id()
        if tenant_id:
            record["extra"]["tenant_id"] = tenant_id
        else:
            record["extra"]["tenant_id"] = "system"
    except ImportError:
        record["extra"]["tenant_id"] = "system"
    return True


# Create a structured logger instance (optional wrapper if needed)
structured_logger = logger
