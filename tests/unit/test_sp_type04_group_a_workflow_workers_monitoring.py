"""
SP-TYPE-04 Group A — AST regression tests for Workflow + Workers + Monitoring type hardening.

Each test parses the source file with the `ast` module and asserts that:
  - Dead legacy typing imports (Dict, Optional, Set, Type, etc.) are gone.
  - New concrete annotations (AsyncEngine, ILLMProvider, dict[str, str], etc.) are present.
  - TODO(TYPE) markers on already-final dict[str, Any] lines are removed.
  - __aexit__ signatures use standard BaseException types, not Any.

These tests have zero runtime dependencies on the modules themselves and
therefore do not trigger any heavy initialisation code.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent  # repo root


def _imported_names(path: Path) -> set[str]:
    """Return every name imported from `typing` or `collections.abc` in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("typing", "collections.abc"):
            for alias in node.names:
                names.add(alias.name)
    return names


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# src/core/workflow/providers.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkflowProvidersTypes:
    """__aexit__ signatures use standard BaseException types; TODO markers on TypeAliases removed."""

    FILE = ROOT / "src/core/workflow/providers.py"

    def test_aexit_uses_base_exception_type(self) -> None:
        """ProductionUnitOfWork.__aexit__ must use type[BaseException] | None, not Any."""
        src = _source(self.FILE)
        assert "exc_type: type[BaseException] | None" in src, (
            "__aexit__ exc_type should be 'type[BaseException] | None', not 'Any'"
        )

    def test_aexit_uses_traceback_type(self) -> None:
        """Both __aexit__ signatures must reference types.TracebackType."""
        src = _source(self.FILE)
        assert "types.TracebackType | None" in src, (
            "__aexit__ exc_tb should be 'types.TracebackType | None', not 'Any'"
        )

    def test_types_module_imported(self) -> None:
        """stdlib `types` must be imported for TracebackType."""
        tree = ast.parse(_source(self.FILE))
        stdlib_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    stdlib_imports.add(alias.name)
        assert "types" in stdlib_imports, "stdlib `types` must be imported for TracebackType"

    def test_type_alias_todo_comments_removed(self) -> None:
        """TODO(TYPE) markers on the three TypeAlias lines must be gone."""
        src = _source(self.FILE)
        assert "LLMResponse: TypeAlias = dict[str, Any]  # TODO" not in src
        assert "ToolResult: TypeAlias = dict[str, Any]  # TODO" not in src
        assert "AgentResponse: TypeAlias = dict[str, Any]  # TODO" not in src


# ---------------------------------------------------------------------------
# src/workers/workflow_worker.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkersWorkflowWorkerTypes:
    """Optional and Type removed; _engine/_async_session_maker use AsyncEngine types."""

    FILE = ROOT / "src/workers/workflow_worker.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in workflow_worker.py — use X | None syntax instead"
        )

    def test_type_not_imported(self) -> None:
        assert "Type" not in _imported_names(self.FILE), (
            "Type is unused in workflow_worker.py — use built-in type[] instead"
        )

    def test_async_engine_variable_annotation(self) -> None:
        """_engine module-level variable must be typed AsyncEngine | None."""
        src = _source(self.FILE)
        assert "_engine: AsyncEngine | None" in src, (
            "_engine should be typed 'AsyncEngine | None', not 'Any | None'"
        )

    def test_async_session_maker_variable_annotation(self) -> None:
        """_async_session_maker must be typed async_sessionmaker[AsyncSession] | None."""
        src = _source(self.FILE)
        assert "_async_session_maker: async_sessionmaker[AsyncSession] | None" in src, (
            "_async_session_maker should use concrete async_sessionmaker[AsyncSession] type"
        )

    def test_get_engine_return_type(self) -> None:
        """get_engine() must return AsyncEngine, not Any."""
        tree = ast.parse(_source(self.FILE))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_engine":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert ret == "AsyncEngine", (
                    f"get_engine() should return 'AsyncEngine', got {ret!r}"
                )
                return
        pytest.fail("get_engine not found in workflow_worker.py")

    def test_get_async_session_maker_return_type(self) -> None:
        """get_async_session_maker() must return async_sessionmaker[AsyncSession], not Any."""
        tree = ast.parse(_source(self.FILE))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_async_session_maker":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert "async_sessionmaker" in ret, (
                    f"get_async_session_maker() should return 'async_sessionmaker[AsyncSession]', got {ret!r}"
                )
                return
        pytest.fail("get_async_session_maker not found in workflow_worker.py")

    def test_type_alias_todo_comments_removed(self) -> None:
        """TODO(TYPE) markers on the two TypeAlias lines must be gone."""
        src = _source(self.FILE)
        assert "WorkflowTaskResult: TypeAlias = dict[str, Any]  # TODO" not in src
        assert "HealthStatus: TypeAlias = dict[str, Any]  # TODO" not in src


# ---------------------------------------------------------------------------
# src/workers/workflow_worker.py -- wees tot 2026-08-27 naar de bevestigd dode
# src/core/workflow/worker.py (ADR-036 OP-158 D2b, verwijderd); dit is de echte,
# gedeployde module.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkflowWorkerTypes:
    """Optional removed; ProviderFactory methods return interface types."""

    FILE = ROOT / "src/workers/workflow_worker.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in worker.py — use X | None syntax instead"
        )

    def test_interface_types_imported(self) -> None:
        """ILLMProvider, IToolBroker, IAgentRuntime must be imported."""
        src = _source(self.FILE)
        assert "ILLMProvider" in src, "ILLMProvider must be imported from interfaces"
        assert "IToolBroker" in src, "IToolBroker must be imported from interfaces"
        assert "IAgentRuntime" in src, "IAgentRuntime must be imported from interfaces"

    def test_create_llm_provider_returns_interface(self) -> None:
        """create_llm_provider() must return ILLMProvider, not Any."""
        tree = ast.parse(_source(self.FILE))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "create_llm_provider":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert ret == "ILLMProvider", (
                    f"create_llm_provider() should return 'ILLMProvider', got {ret!r}"
                )
                return
        pytest.fail("create_llm_provider not found in worker.py")

    def test_create_tool_broker_returns_interface(self) -> None:
        """create_tool_broker() must return IToolBroker, not Any."""
        tree = ast.parse(_source(self.FILE))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "create_tool_broker":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert ret == "IToolBroker", (
                    f"create_tool_broker() should return 'IToolBroker', got {ret!r}"
                )
                return
        pytest.fail("create_tool_broker not found in worker.py")

    def test_set_providers_todo_removed(self) -> None:
        """TODO(TYPE) marker on set_providers must be gone."""
        src = _source(self.FILE)
        assert "set_providers" in src
        assert "def set_providers" in src
        # The old TODO comment must not remain on the set_providers signature line
        assert "def set_providers(\n        cls, llm_class: Any, tool_class: Any" not in src


# ---------------------------------------------------------------------------
# src/core/monitoring/prometheus_metrics.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPrometheusMetricsTypes:
    """Unused legacy imports Dict, Set, Type removed; garbled docstring fixed."""

    FILE = ROOT / "src/core/monitoring/prometheus_metrics.py"

    def test_dict_not_imported(self) -> None:
        assert "Dict" not in _imported_names(self.FILE), (
            "Dict is a legacy typing alias — use built-in dict[] instead"
        )

    def test_set_not_imported(self) -> None:
        assert "Set" not in _imported_names(self.FILE), (
            "Set is a legacy typing alias — use built-in set[] instead"
        )

    def test_type_not_imported(self) -> None:
        assert "Type" not in _imported_names(self.FILE), (
            "Type is a legacy typing alias — use built-in type[] instead"
        )

    def test_self_still_imported(self) -> None:
        """Self is genuinely used in DummyCounter.labels() return type."""
        assert "Self" in _imported_names(self.FILE)

    def test_garbled_docstring_fixed(self) -> None:
        """The garbled 'Dict[str, Any]ionary' docstring line must be replaced."""
        src = _source(self.FILE)
        assert "Dict[str, Any]ionary" not in src, (
            "Garbled docstring 'Dict[str, Any]ionary' must be replaced with plain text"
        )

    def test_get_metrics_info_todo_removed(self) -> None:
        """TODO(TYPE) marker on get_metrics_info signature must be gone."""
        src = _source(self.FILE)
        assert "def get_metrics_info() -> dict[str, Any]:  # TODO" not in src

    def test_get_sla_status_todo_removed(self) -> None:
        """TODO(TYPE) marker on get_sla_status must be gone."""
        src = _source(self.FILE)
        assert "def get_sla_status(self) -> dict[str, Any]:  # TODO" not in src


# ---------------------------------------------------------------------------
# src/core/monitoring/vibe_monitoring.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVibeMonitoringTypes:
    """Private check methods narrowed from dict[str,Any] to dict[str,str]."""

    FILE = ROOT / "src/core/monitoring/vibe_monitoring.py"

    def test_check_llm_returns_str_str_dict(self) -> None:
        """_check_llm must return dict[str, str], not dict[str, Any]."""
        tree = ast.parse(_source(self.FILE))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_check_llm":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert ret == "dict[str, str]", (
                    f"_check_llm() should return 'dict[str, str]', got {ret!r}"
                )
                return
        pytest.fail("_check_llm not found in vibe_monitoring.py")

    def test_check_database_returns_str_str_dict(self) -> None:
        """_check_database must return dict[str, str], not dict[str, Any]."""
        tree = ast.parse(_source(self.FILE))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_check_database":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert ret == "dict[str, str]", (
                    f"_check_database() should return 'dict[str, str]', got {ret!r}"
                )
                return
        pytest.fail("_check_database not found in vibe_monitoring.py")

    def test_check_websocket_returns_str_str_dict(self) -> None:
        """_check_websocket must return dict[str, str], not dict[str, Any]."""
        tree = ast.parse(_source(self.FILE))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_check_websocket":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert ret == "dict[str, str]", (
                    f"_check_websocket() should return 'dict[str, str]', got {ret!r}"
                )
                return
        pytest.fail("_check_websocket not found in vibe_monitoring.py")

    def test_check_all_todo_removed(self) -> None:
        """TODO(TYPE) markers on check_all and its results dict must be gone."""
        src = _source(self.FILE)
        assert "async def check_all(self) -> dict[str, Any]:  # TODO" not in src
        assert "results: dict[str, Any] = {  # TODO" not in src
