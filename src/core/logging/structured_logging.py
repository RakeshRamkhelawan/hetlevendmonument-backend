"""
SC-2.2: Structured Logging Configuration
JSON-formatted logging for production environments.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional
from collections.abc import Callable


class JSONFormatter(logging.Formatter):
    """
    SC-2.2: JSON log formatter for structured logging.

    Outputs logs in JSON format for easy parsing by log aggregators
    like ELK Stack, Datadog, or CloudWatch.
    """

    def __init__(
        self,
        include_timestamp: bool = True,
        include_level: bool = True,
        include_logger: bool = True,
        include_path: bool = True,
        extra_fields: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        super().__init__()
        self.include_timestamp = include_timestamp
        self.include_level = include_level
        self.include_logger = include_logger
        self.include_path = include_path
        self.extra_fields = extra_fields or {}

        # Add service metadata
        self.service_name = os.getenv("SERVICE_NAME", "sanskriti-backend")
        self.environment = os.getenv("ENVIRONMENT", "development")

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

        # Timestamp
        if self.include_timestamp:
            log_data["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Level
        if self.include_level:
            log_data["level"] = record.levelname
            log_data["level_num"] = record.levelno

        # Message
        log_data["message"] = record.getMessage()

        # Logger name
        if self.include_logger:
            log_data["logger"] = record.name

        # File path and line number
        if self.include_path:
            log_data["path"] = f"{record.pathname}:{record.lineno}"
            log_data["function"] = record.funcName

        # Service metadata
        log_data["service"] = self.service_name
        log_data["environment"] = self.environment

        # Exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Extra fields from record
        if hasattr(record, "extra"):
            log_data["extra"] = getattr(record, "extra", {})

        # Request context (if available)
        for attr in ["request_id", "user_id", "tenant_id", "trace_id"]:
            if hasattr(record, attr):
                log_data[attr] = getattr(record, attr)

        # Static extra fields
        log_data.update(self.extra_fields)

        return json.dumps(log_data, default=str)


def setup_structured_logging(
    level: str = "INFO",
    json_output: bool | None = None,
    service_name: str | None = None,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        json_output: Use JSON format (default: True in production)
        service_name: Service name for logs
    """
    # Determine if we should use JSON
    if json_output is None:
        env = os.getenv("ENVIRONMENT", "development")
        json_output = env in ("production", "staging")

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    if json_output:
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Reduce noise from libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logging.info(f"Structured logging configured (JSON: {json_output})")


class LogContext:
    """Context manager for adding extra fields to logs."""

    def __init__(self, **kwargs: Any) -> None:
        self.extra = kwargs
        self._old_factory: Callable[..., logging.LogRecord] | None = None

    def __enter__(self) -> "LogContext":
        self._old_factory = logging.getLogRecordFactory()
        extra = self.extra

        def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            if self._old_factory is None:
                raise RuntimeError("LogRecord factory not initialized")
            record = self._old_factory(*args, **kwargs)
            for key, value in extra.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(factory)
        return self

    def __exit__(self, *args: Any) -> None:
        if self._old_factory is not None:
            logging.setLogRecordFactory(self._old_factory)
