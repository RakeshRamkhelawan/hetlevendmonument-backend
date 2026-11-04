import logging
import os
import sys
from types import FrameType
from typing import Optional

from loguru import logger


class InterceptHandler(logging.Handler):
    """
    Redirect standard logging to Loguru.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        if frame is None:
            frame = logging.currentframe()
        assert frame is not None

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging() -> None:
    """
    Configure Loguru logging based on environment.
    Redirects standard logging to Loguru.
    """
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

    # Remove default handlers
    logger.remove()

    # Determine Sink and Format
    if ENVIRONMENT == "production" or os.getenv("LOG_FORMAT", "").lower() == "json":
        # JSON Output for Production (serialize=True automatically handles JSON)
        logger.add(
            sys.stdout,
            level=LOG_LEVEL,
            serialize=True,
            backtrace=True,
            diagnose=False,  # Secure, don't leak variable values in stack trace
        )
    else:
        # Development: Pretty Print
        logger.add(
            sys.stdout,
            level=LOG_LEVEL,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            backtrace=True,
            diagnose=True,
        )

    # Intercept Standard Logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0)

    # Silence noisy libraries
    for lib in ["uvicorn.access", "uvicorn.error", "uvicorn", "fastapi"]:
        _logger = logging.getLogger(lib)
        _logger.handlers = [InterceptHandler()]
        _logger.propagate = False

    logger.info(f"Logging configured for {ENVIRONMENT} (Level: {LOG_LEVEL})")
