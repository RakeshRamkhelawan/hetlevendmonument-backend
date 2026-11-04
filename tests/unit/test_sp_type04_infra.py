"""
SP-TYPE-04 Group A: Type annotation tests for workflow, workers, monitoring,
database, security, infrastructure, caching, config, auth, and shared modules.

Each class verifies via AST or source-text inspection that:
  - legacy typing imports are removed
  - TODO(TYPE) markers are gone
  - specific local variables / return types / parameters use the correct annotation
"""

import ast
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _parse(rel: str) -> ast.Module:
    return ast.parse(_source(rel))


def _imported_names(rel: str) -> set[str]:
    tree = _parse(rel)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                names.add(alias.name)
    return names


# ---------------------------------------------------------------------------
# providers.py
# ---------------------------------------------------------------------------


class TestWorkflowProvidersTypes:
    FILE = "src/core/workflow/providers.py"

    def test_types_module_imported(self) -> None:
        src = _source(self.FILE)
        assert "import types" in src

    def test_aexit_uses_base_exception_type(self) -> None:
        src = _source(self.FILE)
        assert "exc_type: type[BaseException] | None" in src

    def test_aexit_uses_traceback_type(self) -> None:
        src = _source(self.FILE)
        assert "types.TracebackType | None" in src

    def test_type_alias_todo_comments_removed(self) -> None:
        src = _source(self.FILE)
        # The three TypeAlias lines must not have TODO markers
        for alias in ("LLMResponse", "ToolResult", "AgentResponse"):
            # Find the line with this alias
            for line in src.splitlines():
                if f"{alias}: TypeAlias" in line:
                    assert "TODO" not in line, f"TODO found in {alias} line"
                    break


# ---------------------------------------------------------------------------
# workflow_worker.py (src/workers/)
# ---------------------------------------------------------------------------


class TestWorkersWorkflowWorkerTypes:
    FILE = "src/workers/workflow_worker.py"

    def test_optional_not_imported(self) -> None:
        names = _imported_names(self.FILE)
        assert "Optional" not in names

    def test_type_not_imported(self) -> None:
        names = _imported_names(self.FILE)
        assert "Type" not in names

    def test_async_engine_imported(self) -> None:
        src = _source(self.FILE)
        assert "AsyncEngine" in src

    def test_engine_variable_annotated(self) -> None:
        src = _source(self.FILE)
        assert "_engine: AsyncEngine | None" in src

    def test_session_maker_variable_annotated(self) -> None:
        src = _source(self.FILE)
        assert "_async_session_maker: async_sessionmaker[AsyncSession] | None" in src

    def test_get_engine_return_type(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_engine":
                assert node.returns is not None
                ret = ast.unparse(node.returns)
                assert ret == "AsyncEngine", f"Expected AsyncEngine, got {ret!r}"
                return
        pytest.fail("get_engine not found")

    def test_get_async_session_maker_return_type(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_async_session_maker":
                assert node.returns is not None
                ret = ast.unparse(node.returns)
                assert "async_sessionmaker" in ret
                return
        pytest.fail("get_async_session_maker not found")


# ---------------------------------------------------------------------------
# workflow_worker.py (src/workers/) -- wees tot 2026-08-27 naar de bevestigd dode
# src/core/workflow/worker.py (ADR-036 OP-158 D2b, verwijderd); dit is de echte,
# gedeployde module.
# ---------------------------------------------------------------------------


class TestWorkflowWorkerTypes:
    FILE = "src/workers/workflow_worker.py"

    def test_optional_not_imported(self) -> None:
        names = _imported_names(self.FILE)
        assert "Optional" not in names

    def test_interface_imports_present(self) -> None:
        src = _source(self.FILE)
        assert "ILLMProvider" in src
        assert "IToolBroker" in src
        assert "IAgentRuntime" in src

    def test_create_llm_provider_return_type(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "create_llm_provider":
                assert node.returns is not None
                ret = ast.unparse(node.returns)
                assert ret == "ILLMProvider", f"Expected ILLMProvider, got {ret!r}"
                return
        pytest.fail("create_llm_provider not found")

    def test_create_tool_broker_return_type(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "create_tool_broker":
                assert node.returns is not None
                ret = ast.unparse(node.returns)
                assert ret == "IToolBroker", f"Expected IToolBroker, got {ret!r}"
                return
        pytest.fail("create_tool_broker not found")

    def test_create_agent_runtime_return_type(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "create_agent_runtime":
                assert node.returns is not None
                ret = ast.unparse(node.returns)
                assert ret == "IAgentRuntime", f"Expected IAgentRuntime, got {ret!r}"
                return
        pytest.fail("create_agent_runtime not found")


# ---------------------------------------------------------------------------
# prometheus_metrics.py
# ---------------------------------------------------------------------------


class TestPrometheusMetricsTypes:
    FILE = "src/core/monitoring/prometheus_metrics.py"

    def test_dict_not_imported(self) -> None:
        assert "Dict" not in _imported_names(self.FILE)

    def test_set_not_imported(self) -> None:
        assert "Set" not in _imported_names(self.FILE)

    def test_type_not_imported(self) -> None:
        assert "Type" not in _imported_names(self.FILE)

    def test_self_still_imported(self) -> None:
        assert "Self" in _imported_names(self.FILE)

    def test_get_metrics_info_no_todo(self) -> None:
        src = _source(self.FILE)
        for line in src.splitlines():
            if "def get_metrics_info" in line:
                assert "TODO" not in line
                break

    def test_get_sla_status_no_todo(self) -> None:
        src = _source(self.FILE)
        for line in src.splitlines():
            if "def get_sla_status" in line:
                assert "TODO" not in line
                break

    def test_garbled_docstring_fixed(self) -> None:
        src = _source(self.FILE)
        assert "Dict[str, Any]ionary" not in src


# ---------------------------------------------------------------------------
# vibe_monitoring.py
# ---------------------------------------------------------------------------


class TestVibeMonitoringTypes:
    FILE = "src/core/monitoring/vibe_monitoring.py"

    def test_check_llm_returns_str_str_dict(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_check_llm":
                assert node.returns is not None
                ret = ast.unparse(node.returns)
                assert ret == "dict[str, str]", f"Expected dict[str, str], got {ret!r}"
                return
        pytest.fail("_check_llm not found")

    def test_check_database_returns_str_str_dict(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_check_database":
                assert node.returns is not None
                ret = ast.unparse(node.returns)
                assert ret == "dict[str, str]", f"Expected dict[str, str], got {ret!r}"
                return
        pytest.fail("_check_database not found")

    def test_check_websocket_returns_str_str_dict(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_check_websocket"
            ):
                assert node.returns is not None
                ret = ast.unparse(node.returns)
                assert ret == "dict[str, str]", f"Expected dict[str, str], got {ret!r}"
                return
        pytest.fail("_check_websocket not found")

    def test_no_todo_markers(self) -> None:
        src = _source(self.FILE)
        non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
        assert not non_type_todos, f"Feature TODOs must be gone: {non_type_todos[:2]}"


# ---------------------------------------------------------------------------
# query_optimizer.py
# ---------------------------------------------------------------------------


class TestQueryOptimizerTypes:
    FILE = "src/core/database/query_optimizer.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE)

    def test_engine_imported(self) -> None:
        src = _source(self.FILE)
        assert "from sqlalchemy.engine import Engine" in src

    def test_configure_engine_returns_engine(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "configure_engine":
                assert node.returns is not None
                ret = ast.unparse(node.returns)
                assert ret == "Engine", f"Expected Engine, got {ret!r}"
                return
        pytest.fail("configure_engine not found")

    def test_optimization_log_is_list_str(self) -> None:
        src = _source(self.FILE)
        assert "optimization_log: list[str] = []" in src

    def test_recommendations_is_list_str(self) -> None:
        src = _source(self.FILE)
        assert "recommendations: list[str] = []" in src

    def test_no_todo_markers(self) -> None:
        src = _source(self.FILE)
        non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
        assert not non_type_todos, f"Feature TODOs must be gone: {non_type_todos[:2]}"


# ---------------------------------------------------------------------------
# unit_of_work.py
# ---------------------------------------------------------------------------


class TestUnitOfWorkTypes:
    FILE = "src/core/database/unit_of_work.py"

    def test_async_session_imported(self) -> None:
        src = _source(self.FILE)
        assert "AsyncSession" in src

    def test_async_sessionmaker_imported(self) -> None:
        src = _source(self.FILE)
        assert "async_sessionmaker" in src

    def test_traceback_type_imported(self) -> None:
        src = _source(self.FILE)
        assert "TracebackType" in src

    def test_aexit_uses_base_exception(self) -> None:
        src = _source(self.FILE)
        assert "type[BaseException] | None" in src

    def test_session_property_returns_async_session(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "session":
                if node.returns is not None:
                    ret = ast.unparse(node.returns)
                    assert ret == "AsyncSession", f"Expected AsyncSession, got {ret!r}"
                    return
        pytest.fail("session property not found")

    def test_no_todo_markers(self) -> None:
        src = _source(self.FILE)
        non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
        assert not non_type_todos, f"Feature TODOs must be gone: {non_type_todos[:2]}"


# ---------------------------------------------------------------------------
# query_analyzer.py
# ---------------------------------------------------------------------------


class TestQueryAnalyzerTypes:
    FILE = "src/core/database/query_analyzer.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE)

    def test_engine_imported(self) -> None:
        src = _source(self.FILE)
        assert "from sqlalchemy.engine import Engine" in src

    def test_setup_query_logging_engine_param(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "setup_query_logging":
                first_arg = node.args.args[0]
                assert first_arg.annotation is not None
                ann = ast.unparse(first_arg.annotation)
                assert ann == "Engine", f"Expected Engine, got {ann!r}"
                return
        pytest.fail("setup_query_logging not found")

    def test_potential_n_plus_one_is_list_dict(self) -> None:
        src = _source(self.FILE)
        assert "potential_n_plus_one: list[dict[str, str | int]]" in src

    def test_no_todo_markers(self) -> None:
        src = _source(self.FILE)
        non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
        assert not non_type_todos, f"Feature TODOs must be gone: {non_type_todos[:2]}"


# ---------------------------------------------------------------------------
# database.py
# ---------------------------------------------------------------------------


class TestDatabaseTypes:
    FILE = "src/core/database/database.py"

    def test_set_not_imported(self) -> None:
        assert "Set" not in _imported_names(self.FILE)

    def test_no_todo_markers(self) -> None:
        src = _source(self.FILE)
        non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
        assert not non_type_todos, f"Feature TODOs must be gone: {non_type_todos[:2]}"


# ---------------------------------------------------------------------------
# retry_logic.py
# ---------------------------------------------------------------------------


class TestRetryLogicTypes:
    FILE = "src/core/database/retry_logic.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE)

    def test_cast_not_imported(self) -> None:
        assert "cast" not in _imported_names(self.FILE)

    def test_no_todo_markers(self) -> None:
        src = _source(self.FILE)
        non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
        assert not non_type_todos, f"Feature TODOs must be gone: {non_type_todos[:2]}"


# ---------------------------------------------------------------------------
# tenant_validation.py
# ---------------------------------------------------------------------------


class TestTenantValidationTypes:
    FILE = "src/core/security/tenant_validation.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE)

    def test_aexit_uses_base_exception(self) -> None:
        src = _source(self.FILE)
        assert "type[BaseException] | None" in src


# ---------------------------------------------------------------------------
# input_sanitization.py
# ---------------------------------------------------------------------------


class TestInputSanitizationTypes:
    FILE = "src/core/security/input_sanitization.py"

    def test_no_legacy_typing_imports(self) -> None:
        names = _imported_names(self.FILE)
        for legacy in ("Dict", "List", "Optional", "Union", "Type"):
            assert legacy not in names, f"Legacy import {legacy!r} still present"


# ---------------------------------------------------------------------------
# rls_validation.py
# ---------------------------------------------------------------------------


class TestRlsValidationTypes:
    FILE = "src/core/security/rls_validation.py"

    def test_no_legacy_typing_imports(self) -> None:
        names = _imported_names(self.FILE)
        for legacy in ("List", "Optional", "Type", "Union"):
            assert legacy not in names, f"Legacy import {legacy!r} still present"


# ---------------------------------------------------------------------------
# egress_aware_client.py
# ---------------------------------------------------------------------------


class TestEgressAwareClientTypes:
    FILE = "src/core/security/egress_aware_client.py"

    def test_exc_tb_not_any(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "__aexit__":
                args_by_name = {arg.arg: arg for arg in node.args.args}
                exc_tb_arg = args_by_name.get("exc_tb")
                assert exc_tb_arg is not None, "exc_tb argument not found"
                ann = exc_tb_arg.annotation
                assert ann is not None
                assert not (isinstance(ann, ast.Name) and ann.id == "Any"), (
                    "exc_tb must not be annotated as Any"
                )
                return
        pytest.fail("__aexit__ not found in EgressAwareAsyncClient")


# ---------------------------------------------------------------------------
# redis_cache.py
# ---------------------------------------------------------------------------


class TestRedisCacheTypes:
    FILE = "src/core/infrastructure/redis_cache.py"

    def test_no_legacy_typing_imports(self) -> None:
        names = _imported_names(self.FILE)
        for legacy in ("Dict", "List", "Optional", "Set"):
            assert legacy not in names, f"Legacy import {legacy!r} still present"

    def test_keys_not_list_any(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "keys":
                    ann = node.annotation
                    if isinstance(ann, ast.Subscript):
                        slice_node = ann.slice
                        assert not (isinstance(slice_node, ast.Name) and slice_node.id == "Any"), (
                            "keys annotation must not be list[Any]"
                        )


# ---------------------------------------------------------------------------
# cache_decorators.py
# ---------------------------------------------------------------------------


class TestCacheDecoratorsTypes:
    FILE = "src/core/caching/cache_decorators.py"

    def test_no_legacy_typing_imports(self) -> None:
        names = _imported_names(self.FILE)
        for legacy in ("List", "Optional", "Set", "Type"):
            assert legacy not in names, f"Legacy import {legacy!r} still present"


# ---------------------------------------------------------------------------
# cache_layer.py
# ---------------------------------------------------------------------------


class TestCacheLayerTypes:
    FILE = "src/core/caching/cache_layer.py"

    def test_no_legacy_typing_imports(self) -> None:
        names = _imported_names(self.FILE)
        for legacy in ("Dict", "Optional", "Set"):
            assert legacy not in names, f"Legacy import {legacy!r} still present"

    def test_get_stats_no_todo(self) -> None:
        src = _source(self.FILE)
        for line in src.splitlines():
            if "def get_stats" in line:
                assert "TODO" not in line
                break


# ---------------------------------------------------------------------------
# unified_config.py
# ---------------------------------------------------------------------------


class TestUnifiedConfigTypes:
    FILE = "src/core/config/unified_config.py"

    def test_no_legacy_typing_dict_list_tuple(self) -> None:
        names = _imported_names(self.FILE)
        for legacy in ("Dict", "List", "Tuple"):
            assert legacy not in names, f"Legacy import {legacy!r} still present"

    def test_files_list_is_str(self) -> None:
        src = _source(self.FILE)
        assert "files: list[str] = []" in src

    def test_issues_list_is_str(self) -> None:
        src = _source(self.FILE)
        assert "issues: list[str] = []" in src

    def test_warnings_list_is_str(self) -> None:
        src = _source(self.FILE)
        assert "warnings: list[str] = []" in src

    def test_no_todo_markers(self) -> None:
        src = _source(self.FILE)
        non_type_todos = [ln for ln in src.splitlines() if "TODO" in ln and "(TYPE)" not in ln]
        assert not non_type_todos, f"Feature TODOs must be gone: {non_type_todos[:2]}"

    def test_validate_jwt_secret_typed(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "validate_jwt_secret"
            ):
                if node.returns is not None:
                    ret = ast.unparse(node.returns)
                    assert ret == "str", f"Expected str return, got {ret!r}"
                    return
        pytest.fail("validate_jwt_secret not found")


# ---------------------------------------------------------------------------
# jwt_handler.py
# ---------------------------------------------------------------------------


class TestJwtHandlerTypes:
    FILE = "src/core/auth/jwt_handler.py"

    def test_decoded_not_bare_any(self) -> None:
        tree = _parse(self.FILE)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "decoded":
                    ann = node.annotation
                    assert not (isinstance(ann, ast.Name) and ann.id == "Any"), (
                        "decoded must not be annotated as plain Any"
                    )
                    found = True
        assert found, "AnnAssign for decoded not found in jwt_handler.py"


# ---------------------------------------------------------------------------
# rbac_decorator.py
# ---------------------------------------------------------------------------


class TestRbacDecoratorTypes:
    FILE = "src/core/auth/rbac_decorator.py"

    def test_no_legacy_typing_imports(self) -> None:
        names = _imported_names(self.FILE)
        for legacy in ("Tuple", "Type"):
            assert legacy not in names, f"Legacy import {legacy!r} still present"


# ---------------------------------------------------------------------------
# llm_client.py
# ---------------------------------------------------------------------------


class TestLlmClientTypes:
    FILE = "src/core/shared/llm_client.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE)

    def test_openai_messages_not_list_any(self) -> None:
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "openai_messages":
                    ann = node.annotation
                    if isinstance(ann, ast.Subscript):
                        slice_node = ann.slice
                        assert not (isinstance(slice_node, ast.Name) and slice_node.id == "Any"), (
                            "openai_messages still annotated as list[Any]"
                        )


# ---------------------------------------------------------------------------
# response_cache.py
# ---------------------------------------------------------------------------


class TestResponseCacheTypes:
    FILE = "src/core/shared/response_cache.py"

    def test_no_legacy_typing_imports(self) -> None:
        names = _imported_names(self.FILE)
        for legacy in ("Dict", "List", "Optional"):
            assert legacy not in names, f"Legacy import {legacy!r} still present"

    def test_health_issues_is_list_str(self) -> None:
        tree = _parse(self.FILE)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "health_issues":
                    ann = node.annotation
                    assert isinstance(ann, ast.Subscript), "health_issues should be subscript type"
                    slice_node = ann.slice
                    assert not (isinstance(slice_node, ast.Name) and slice_node.id == "Any"), (
                        "health_issues must not be list[Any]"
                    )
                    assert isinstance(slice_node, ast.Name) and slice_node.id == "str", (
                        f"Expected list[str], got {ast.dump(slice_node)}"
                    )
                    found = True
        assert found, "AnnAssign for health_issues not found"


# ---------------------------------------------------------------------------
# production_logging.py
# ---------------------------------------------------------------------------


class TestProductionLoggingTypes:
    FILE = "src/core/shared/production_logging.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE)

    def test_details_is_list_str(self) -> None:
        tree = _parse(self.FILE)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "details":
                    ann = node.annotation
                    assert isinstance(ann, ast.Subscript), "details should be list[str]"
                    slice_node = ann.slice
                    assert not (isinstance(slice_node, ast.Name) and slice_node.id == "Any"), (
                        "details must not be list[Any]"
                    )
                    assert isinstance(slice_node, ast.Name) and slice_node.id == "str", (
                        f"Expected list[str], got {ast.dump(slice_node)}"
                    )
                    found = True
        assert found, "AnnAssign for details not found in production_logging.py"
