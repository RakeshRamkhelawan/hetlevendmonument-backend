"""Unit tests for scripts/codebase_inventory.py.

Verifies that:
1. Protocol interface definitions (typing.Protocol with ...) are NOT classified as hollow.
2. Abstract methods (@abstractmethod with pass or ...) are NOT classified as hollow.
3. Genuine hollow stubs (pass, ..., empty return in normal classes) ARE classified as hollow.
4. Functions claiming success without work ARE classified as success_no_work.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "_codebase_inventory_under_test",
    Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "codebase_inventory.py",
)
assert _SPEC and _SPEC.loader
_inv_module = importlib.util.module_from_spec(_SPEC)
sys.modules["_codebase_inventory_under_test"] = _inv_module
_SPEC.loader.exec_module(_inv_module)

classify_function = _inv_module.classify_function
analyse_source = getattr(_inv_module, "analyse_source", None)
ModuleInfo = _inv_module.ModuleInfo


@pytest.mark.unit
def test_protocol_methods_not_classified_as_hollow() -> None:
    """Methods with ... inside a Protocol class must be recognized as interface contracts."""
    code = """
from typing import Protocol

class RedisClient(Protocol):
    def get(self, key: str) -> str:
        ...

    def set(self, key: str, value: str) -> bool:
        ...
"""
    tree = ast.parse(code)
    # When analyzed, RedisClient.get and RedisClient.set should NOT be in hollow
    info = _inv_module.analyse_tree(
        tree,
        module="src.core.typing.redis_protocol",
        path="src/core/typing/redis_protocol.py",
    )
    assert "get" not in info.hollow
    assert "set" not in info.hollow
    assert len(info.hollow) == 0


@pytest.mark.unit
def test_abstract_methods_not_classified_as_hollow() -> None:
    """Methods decorated with @abstractmethod must be recognized as interface contracts."""
    code = """
from abc import ABC, abstractmethod

class BaseProcessor(ABC):
    @abstractmethod
    def process(self, item: dict) -> bool:
        pass

    @abstractmethod
    def validate(self, item: dict) -> bool:
        ...
"""
    tree = ast.parse(code)
    info = _inv_module.analyse_tree(
        tree,
        module="src.core.processor",
        path="src/core/processor.py",
    )
    assert "process" not in info.hollow
    assert "validate" not in info.hollow
    assert len(info.hollow) == 0


@pytest.mark.unit
def test_regular_hollow_function_classified_as_hollow() -> None:
    """Regular functions or methods with pass or empty returns must be classified as hollow."""
    code = """
def dummy_standalone():
    pass

class RegularWorker:
    def work(self):
        ...

    def empty_list(self):
        return []
"""
    tree = ast.parse(code)
    info = _inv_module.analyse_tree(
        tree,
        module="src.core.worker",
        path="src/core/worker.py",
    )
    assert "dummy_standalone" in info.hollow
    assert "work" in info.hollow
    assert "empty_list" in info.hollow


@pytest.mark.unit
def test_success_no_work_classified_correctly() -> None:
    """Functions returning fake success dicts must be classified as success_no_work."""
    code = """
class FakeSupervisor:
    def act(self):
        return {"status": "success", "data": None}

    def dispatch(self):
        return X(status="completed")
"""
    tree = ast.parse(code)
    info = _inv_module.analyse_tree(
        tree,
        module="src.core.fake",
        path="src/core/fake.py",
    )
    assert "act" in info.success_no_work
    assert "dispatch" in info.success_no_work


@pytest.mark.unit
def test_overload_signatures_not_classified_as_hollow() -> None:
    """Overload declarations (@overload with ...) must be recognized as type contracts."""
    code = """
from typing import Callable, overload

@overload
def register_handler(event_type: str) -> Callable:
    ...

@overload
def register_handler(event_type: str, handler: Callable) -> Callable:
    ...

def register_handler(event_type: str, handler: Callable | None = None) -> Callable:
    return handler or (lambda f: f)
"""
    tree = ast.parse(code)
    info = _inv_module.analyse_tree(
        tree,
        module="src.core.events.handlers",
        path="src/core/events/handlers/__init__.py",
    )
    assert len(info.hollow) == 0


@pytest.mark.unit
def test_import_error_fallback_stub_classes_not_classified_as_hollow() -> None:
    """Fallback stub classes defined inside except ImportError blocks must be ignored."""
    code = """
try:
    from external_pkg import RealService
except ImportError:
    class RealService:
        def __init__(self, *args: object, **kwargs: object) -> None:
            ...

        def process(self, data: dict) -> None:
            pass
"""
    tree = ast.parse(code)
    info = _inv_module.analyse_tree(
        tree,
        module="src.core.services.external",
        path="src/core/services/external.py",
    )
    assert len(info.hollow) == 0


@pytest.mark.unit
def test_context_manager_exit_returning_false_not_classified_as_hollow() -> None:
    """Context manager __aexit__ and __exit__ returning False (PEP 492/343) must not be hollow."""
    code = """
class SessionContext:
    async def __aexit__(self, *args) -> bool | None:
        return False

class SyncContext:
    def __exit__(self, *args) -> bool:
        return False
"""
    tree = ast.parse(code)
    info = _inv_module.analyse_tree(
        tree,
        module="src.core.context",
        path="src/core/context.py",
    )
    assert len(info.hollow) == 0


@pytest.mark.unit
def test_base_class_template_hooks_not_classified_as_hollow() -> None:
    """Methods raising NotImplementedError in classes with Base/Strategy/Supervisor prefix/suffix are legitimate hooks."""
    code = """
class BaseSupervisor:
    async def decompose_task(self, task: dict):
        raise NotImplementedError

class AgentSelectionStrategy:
    def select_agent(self, candidates: list):
        raise NotImplementedError("Subclasses must implement")

class RegularService:
    def normal_method_not_implemented(self):
        raise NotImplementedError
"""
    tree = ast.parse(code)
    info = _inv_module.analyse_tree(
        tree,
        module="src.core.als.supervisors",
        path="src/core/als/supervisors/base_supervisor.py",
    )
    assert "decompose_task" not in info.hollow
    assert "select_agent" not in info.hollow
    assert "normal_method_not_implemented" in info.hollow

