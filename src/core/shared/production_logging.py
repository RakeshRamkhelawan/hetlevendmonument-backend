import logging
import sys
from typing import Any


def log_startup_validation() -> bool:
    # This is a placeholder. In a real application, this would
    # check for essential configurations, database connections, etc.
    return True


def log_component_health(
    component: str, status: str, message: str, duration: float | None = None
) -> None:
    extra = f" duration={duration:.3f}s" if duration is not None else ""
    production_logger.info(
        "component=%s status=%s message=%s%s",
        component,
        status,
        message,
        extra,
    )


def log_llm_provider_status(
    provider: str,
    model: str,
    status: str,
    response_time: float | None = None,
    error_message: str | None = None,
) -> None:
    details: list[str] = []
    if response_time is not None:
        details.append(f"response_time={response_time:.3f}s")
    if error_message:
        details.append(f"error={error_message}")
    suffix = f" {' '.join(details)}" if details else ""
    production_logger.info(
        "provider=%s model=%s status=%s%s",
        provider,
        model,
        status,
        suffix,
    )


def log_critical_error(
    error_type: str, error: Exception, context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
) -> None:
    if context:
        production_logger.critical(
            "error_type=%s error=%s context=%s",
            error_type,
            error,
            context,
        )
        return None
    production_logger.critical("error_type=%s error=%s", error_type, error)


def log_performance_metrics(
    metric_name: str,
    value: float,
    success: bool,
    details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> None:
    if details:
        production_logger.info(
            "metric=%s value=%s success=%s details=%s",
            metric_name,
            value,
            success,
            details,
        )
        return None
    production_logger.info("metric=%s value=%s success=%s", metric_name, value, success)


class SafeLogger:
    def __init__(self, name: str) -> None:
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # Avoid adding handlers if they already exist
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def info(self, msg: object, *args: object, **kwargs: Any) -> None:
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg: object, *args: object, **kwargs: Any) -> None:
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg: object, *args: object, **kwargs: Any) -> None:
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg: object, *args: object, **kwargs: Any) -> None:
        self.logger.critical(msg, *args, **kwargs)

    def debug(self, msg: object, *args: object, **kwargs: Any) -> None:
        self.logger.debug(msg, *args, **kwargs)

    def exception(self, msg: object, *args: object, **kwargs: Any) -> None:
        self.logger.exception(msg, *args, **kwargs)


production_logger = SafeLogger("production")
