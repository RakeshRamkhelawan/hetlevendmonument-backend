"""Automatic learning decorators for agent method execution."""

from __future__ import annotations

import inspect
import time
from functools import wraps
from typing import Any, cast
from collections.abc import Callable

from src.core.agents.learning_loop import LearningType
from src.core.shared.interfaces import ExecutionResult, TaskData


def _truncate(value: Any, max_arg_length: int) -> str:  # TODO(TYPE): replace Any with concrete type
    rendered = repr(value)
    if len(rendered) <= max_arg_length:
        return rendered
    return rendered[: max_arg_length - 3] + "..."


def _build_args_snapshot(
    args: tuple[Any, ...],  # TODO(TYPE): replace Any with concrete type
    kwargs: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    max_arg_length: int,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    return {
        "args": [_truncate(arg, max_arg_length) for arg in args],
        "kwargs": {key: _truncate(value, max_arg_length) for key, value in kwargs.items()},
    }


def auto_learn(
    learning_type: LearningType = LearningType.PERFORMANCE_OPTIMIZATION,
    max_arg_length: int = 250,
    enabled: bool = True,
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """Record learning observations around decorated method execution."""

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
                if not enabled or not getattr(self, "_learning_enabled", False):
                    return await func(self, *args, **kwargs)

                start = time.perf_counter()
                task_arg = next((arg for arg in args if isinstance(arg, TaskData)), None)
                args_snapshot = _build_args_snapshot(args, kwargs, max_arg_length)

                try:
                    result = await func(self, *args, **kwargs)
                except Exception as exc:
                    duration = time.perf_counter() - start
                    try:
                        await self._record_method_observation(
                            method_name=func.__name__,
                            args_snapshot=args_snapshot,
                            result_snapshot={"success": False, "error": str(exc)},
                            duration_seconds=duration,
                            learning_type=learning_type,
                        )
                    except Exception:
                        pass
                    raise

                duration = time.perf_counter() - start
                try:
                    if task_arg is not None and isinstance(result, ExecutionResult):
                        await self._record_task_observation(task_arg, result)
                    else:
                        success = True
                        if isinstance(result, dict):
                            success = bool(result.get("success", True))
                        await self._record_method_observation(
                            method_name=func.__name__,
                            args_snapshot=args_snapshot,
                            result_snapshot={
                                "success": success,
                                "result": _truncate(result, max_arg_length),
                            },
                            duration_seconds=duration,
                            learning_type=learning_type,
                        )
                except Exception:
                    pass

                return result

            return async_wrapper

        @wraps(func)
        def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            return func(self, *args, **kwargs)

        return cast(Callable[..., Any], sync_wrapper)  # TODO(TYPE): replace Any with concrete type

    return decorator
