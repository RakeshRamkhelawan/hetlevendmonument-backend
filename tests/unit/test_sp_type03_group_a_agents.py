"""
SP-TYPE-03 Group A — AST regression tests for high-Any agent files.

Covers:
  - src/core/agents/performance_optimizer.py
  - src/core/agents/workflow_orchestrator_agent.py
  - src/core/agents/executor_agent.py
  - src/core/agents/cva_agent.py
  - src/core/agents/base_agent.py

AST-only: no production imports, zero side-effects at collection time.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _parse(rel: str) -> ast.Module:
    path = ROOT / rel
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _typing_imports(rel: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_parse(rel)):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                names.add(alias.name)
    return names


# ===========================================================================
# performance_optimizer.py
# ===========================================================================


@pytest.mark.unit
def test_performance_optimizer_cache_instances_dict_typed() -> None:
    """_cache_instances module-level var must be dict[str, LRUCache[Any]]."""
    src = _source("src/core/agents/performance_optimizer.py")
    assert "dict[str, LRUCache[Any]]" in src, (
        "_cache_instances must be typed as dict[str, LRUCache[Any]]; "
        "the inner Any is intentional — the cache is generic over T."
    )


# ===========================================================================
# workflow_orchestrator_agent.py
# ===========================================================================


@pytest.mark.unit
def test_workflow_orchestrator_legacy_imports_removed() -> None:
    """Dict, List, Set, Tuple must not be imported from typing."""
    leaked = {"Dict", "List", "Set", "Tuple"} & _typing_imports(
        "src/core/agents/workflow_orchestrator_agent.py"
    )
    assert not leaked, f"Legacy typing names still imported: {leaked}"


@pytest.mark.unit
def test_workflow_orchestrator_fallback_suggestions_list_concrete() -> None:
    """suggestions local var in _fallback_suggestions must be list[dict[str, Any]]."""
    src = _source("src/core/agents/workflow_orchestrator_agent.py")
    assert "suggestions: list[dict[str," in src
    assert "suggestions: list[Any]" not in src


@pytest.mark.unit
def test_workflow_orchestrator_validated_list_concrete() -> None:
    """validated local var in _validate_suggestions must be list[dict[str, Any]]."""
    src = _source("src/core/agents/workflow_orchestrator_agent.py")
    assert "validated: list[dict[str," in src
    assert "validated: list[Any]" not in src


# ===========================================================================
# executor_agent.py
# ===========================================================================


@pytest.mark.unit
def test_executor_agent_http_session_typed_as_client_session() -> None:
    """http_session must be aiohttp.ClientSession | None, not Any | None."""
    src = _source("src/core/agents/executor_agent.py")
    assert "aiohttp.ClientSession | None" in src
    assert "http_session: Any | None" not in src


@pytest.mark.unit
def test_executor_agent_sandbox_manager_typed_as_base_sandbox_manager() -> None:
    """sandbox_manager must be BaseSandboxManager | None, not Any | None."""
    src = _source("src/core/agents/executor_agent.py")
    assert "BaseSandboxManager | None" in src
    assert "sandbox_manager: Any | None" not in src


@pytest.mark.unit
def test_executor_agent_workflow_steps_concrete_list() -> None:
    """workflow_steps must be list[dict[str, Any]] (dicts proven by loop body)."""
    src = _source("src/core/agents/executor_agent.py")
    assert "workflow_steps: list[dict[str," in src
    assert "workflow_steps: list[Any]" not in src


@pytest.mark.unit
def test_executor_agent_recipients_list_str() -> None:
    """recipients must be list[str] — notification recipients are always strings."""
    src = _source("src/core/agents/executor_agent.py")
    assert "recipients: list[str]" in src
    assert "recipients: list[Any]" not in src


@pytest.mark.unit
def test_executor_agent_file_paths_list_str() -> None:
    """file_paths must be list[str] — file paths are always strings."""
    src = _source("src/core/agents/executor_agent.py")
    assert "file_paths: list[str]" in src
    assert "file_paths: list[Any]" not in src


# ===========================================================================
# cva_agent.py
# ===========================================================================


@pytest.mark.unit
def test_cva_agent_llm_clients_dict_value_is_llm_client() -> None:
    """_llm_clients property and setter must use dict[str, LLMClient], not dict[str, Any]."""
    src = _source("src/core/agents/cva_agent.py")
    assert "dict[str, LLMClient]" in src, (
        "_llm_clients property/setter must return/accept dict[str, LLMClient]"
    )


@pytest.mark.unit
def test_cva_agent_execute_llm_request_first_param_is_llm_client() -> None:
    """_execute_llm_request must accept LLMClient as first positional param, not Any."""
    src = _source("src/core/agents/cva_agent.py")
    idx = src.find("async def _execute_llm_request")
    assert idx != -1
    snippet = src[idx : idx + 300]
    assert "llm_client: ChatTaalmodel" in snippet
    assert "llm_client: Any" not in snippet


@pytest.mark.unit
def test_cva_agent_kwargs_typed_dict_str_str() -> None:
    """kwargs in _execute_llm_request must be dict[str, str] (only 'model' key inserted)."""
    src = _source("src/core/agents/cva_agent.py")
    assert "kwargs: dict[str, str]" in src


# ===========================================================================
# base_agent.py
# ===========================================================================


@pytest.mark.unit
def test_base_agent_dict_and_set_imports_removed() -> None:
    """Dict and Set must not be imported from typing in base_agent.py."""
    leaked = {"Dict", "Set"} & _typing_imports("src/core/agents/base_agent.py")
    assert not leaked, f"Legacy typing names still imported in base_agent.py: {leaked}"


@pytest.mark.unit
def test_base_agent_optional_still_imported() -> None:
    """Optional must remain — used for yaml_config: Optional['AgentConfig']."""
    assert "Optional" in _typing_imports("src/core/agents/base_agent.py")


@pytest.mark.unit
def test_base_agent_tool_broker_returns_tool_broker_service() -> None:
    """tool_broker property and _create_tool_broker must return 'ToolBrokerService', not Any."""
    src = _source("src/core/agents/base_agent.py")
    # Deferred string annotation used to avoid circular import
    assert '"ToolBrokerService"' in src, (
        "tool_broker and _create_tool_broker must annotate return as "
        '"ToolBrokerService" (deferred string ref)'
    )
    # Neither of the two methods should still declare -> Any:
    bad_lines = [
        line
        for line in src.splitlines()
        if "-> Any" in line and ("tool_broker" in line or "_create_tool_broker" in line)
    ]
    assert bad_lines == [], (
        f"tool_broker / _create_tool_broker must not return Any. "
        f"Offending lines: {bad_lines}"
    )
