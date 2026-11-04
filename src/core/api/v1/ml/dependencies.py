"""ML domain dependencies.

The tool predictor is loaded lazily so that importing the ML router during
startup does not block on model/ML stack initialization.
"""

import importlib
from typing import Any

_LAZY_NAMES: dict[str, str] = {
    "get_tool_predictor": "src.core.ml.tool_predictor",
}

__all__ = ["get_tool_predictor"]  # noqa: F822 -- resolved via __getattr__ lazy-load


def __getattr__(name: str) -> Any:
    module_path = _LAZY_NAMES.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_path)
    return getattr(module, name)
