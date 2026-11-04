"""
SP-TYPE-03 Group A Agents — AST-based type annotation regression tests.

All tests are purely static (AST/source inspection). No imports of src modules
at collection time, so they work without a running database or LLM.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import typing

import pytest

ROOT = pathlib.Path(__file__).parent.parent.parent


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _typing_imports(rel: str) -> set[str]:
    src = _source(rel)
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                names.add(alias.name)
    return names


# ---------------------------------------------------------------------------
# workflow_orchestrator_agent.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_workflow_orchestrator_fallback_suggestions_list_concrete() -> None:
    src = _source("src/core/agents/workflow_orchestrator_agent.py")
    assert "suggestions: list[dict[str, Any]]" in src or "suggestions: list[Any]" not in src


@pytest.mark.unit
def test_workflow_orchestrator_validated_list_concrete() -> None:
    src = _source("src/core/agents/workflow_orchestrator_agent.py")
    assert "validated: list[dict[str, Any]]" in src or "validated: list[Any]" not in src


# ---------------------------------------------------------------------------
# executor_agent.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_executor_agent_http_session_typed_as_client_session() -> None:
    src = _source("src/core/agents/executor_agent.py")
    assert "aiohttp.ClientSession | None" in src
    assert "http_session: Any | None" not in src


@pytest.mark.unit
def test_executor_agent_sandbox_manager_typed_as_base_sandbox_manager() -> None:
    src = _source("src/core/agents/executor_agent.py")
    assert "BaseSandboxManager | None" in src
    assert "sandbox_manager: Any | None" not in src


# ---------------------------------------------------------------------------
# cva_agent.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cva_agent_llm_clients_dict_value_is_llm_client() -> None:
    src = _source("src/core/agents/cva_agent.py")
    assert "dict[str, LLMClient]" in src


@pytest.mark.unit
def test_cva_agent_execute_llm_request_first_param_is_llm_client() -> None:
    src = _source("src/core/agents/cva_agent.py")
    idx = src.find("async def _execute_llm_request")
    assert idx != -1, "_execute_llm_request not found"
    snippet = src[idx : idx + 300]
    assert "llm_client: ChatTaalmodel" in snippet
    assert "llm_client: Any" not in snippet


@pytest.mark.unit
def test_cva_agent_kwargs_typed_dict_str_str() -> None:
    src = _source("src/core/agents/cva_agent.py")
    assert "kwargs: dict[str, str]" in src


# ---------------------------------------------------------------------------
# base_agent.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_base_agent_dict_and_set_imports_removed() -> None:
    leaked = {"Dict", "Set"} & _typing_imports("src/core/agents/base_agent.py")
    assert not leaked, f"Legacy imports still present: {leaked}"


@pytest.mark.unit
def test_base_agent_tool_broker_returns_tool_broker_service() -> None:
    src = _source("src/core/agents/base_agent.py")
    assert '"ToolBrokerService"' in src
    bad = [
        line
        for line in src.splitlines()
        if "-> Any" in line and ("tool_broker" in line or "_create_tool_broker" in line)
    ]
    assert bad == [], f"tool_broker/create_tool_broker still returns Any: {bad}"


# ---------------------------------------------------------------------------
# als/router.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_router_optional_import_removed() -> None:
    leaked = {"Optional"} & _typing_imports("src/core/als/router.py")
    assert not leaked, f"Optional still imported in router.py: {leaked}"


@pytest.mark.unit
def test_router_fallback_department_annotation() -> None:
    src = _source("src/core/als/router.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_fallback":
            args = node.args.args
            dept_arg = next((a for a in args if a.arg == "department"), None)
            assert dept_arg is not None, "_fallback must have department arg"
            assert dept_arg.annotation is not None, "department must be annotated"
            ann = dept_arg.annotation
            assert not (isinstance(ann, ast.Name) and ann.id == "Any"), (
                "department should not be plain Any"
            )
            return
    pytest.fail("_fallback method not found in router module")


# ---------------------------------------------------------------------------
# als/models/collective_knowledge.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_collective_knowledge_optional_import_removed() -> None:
    leaked = {"Optional"} & _typing_imports("src/core/als/models/collective_knowledge.py")
    assert not leaked


@pytest.mark.unit
def test_collective_knowledge_validator_annotations() -> None:
    src = _source("src/core/als/models/collective_knowledge.py")
    tree = ast.parse(src)
    found: dict[str, str | None] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "validate_tenant_id",
            "validate_confidence",
        ):
            ret = node.returns
            found[node.name] = ast.unparse(ret) if ret else None
    assert "validate_tenant_id" in found
    assert found["validate_tenant_id"] == "int", (
        f"validate_tenant_id return should be int, got {found['validate_tenant_id']}"
    )
    assert "validate_confidence" in found
    assert "float" in (found["validate_confidence"] or ""), (
        f"validate_confidence return should include float, got {found['validate_confidence']}"
    )


# ---------------------------------------------------------------------------
# agents/ethical_knowledge_graph.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ethical_kg_optional_import_removed() -> None:
    leaked = {"Optional"} & _typing_imports("src/core/agents/ethical_knowledge_graph.py")
    assert not leaked


@pytest.mark.unit
def test_ethical_kg_local_var_annotations() -> None:
    src = _source("src/core/agents/ethical_knowledge_graph.py")
    tree = ast.parse(src)
    any_annassigns = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            ann = node.annotation
            if isinstance(ann, ast.Name) and ann.id == "Any":
                any_annassigns.append((node.target.id, ast.unparse(node)))
    for var_name, assign in any_annassigns:
        assert var_name not in (
            "concept_path",
            "similar_concepts",
            "center_ids",
            "principle_ids",
        ), f"{var_name} should not be plain Any: {assign}"


@pytest.mark.unit
def test_ethical_kg_concrete_list_types() -> None:
    src = _source("src/core/agents/ethical_knowledge_graph.py")
    assert "concept_path: list[str] = []" in src
    assert "similar_concepts: list[tuple[str, float]] = []" in src
    assert "subgraph_relationships: list[KnowledgeRelationship] = []" in src
    assert "conflicts: list[dict[str, Any]] = []" in src
    assert "principle_ids: dict[str, str] = {}" in src


# ---------------------------------------------------------------------------
# agents/subagent_loader.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_subagent_loader_legacy_imports_removed() -> None:
    leaked = {"Dict", "List", "Optional", "Type", "Union"} & _typing_imports(
        "src/core/agents/subagent_loader.py"
    )
    assert not leaked, f"Legacy imports: {leaked}"


@pytest.mark.unit
def test_subagent_loader_concrete_list_annotations() -> None:
    src = _source("src/core/agents/subagent_loader.py")
    assert "discovered_agents: list[AgentDefinition] = []" in src
    assert "agent_definitions: list[AgentDefinition] = []" in src
    assert "results: dict[str, bool] = {}" in src
    assert "status_counts: dict[str, int] = {}" in src
    assert "type_counts: dict[str, int] = {}" in src
    assert "health_monitor_task: asyncio.Task[None] | None = None" in src


# ---------------------------------------------------------------------------
# agents/corrective_rag_agent.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_corrective_rag_no_legacy_typing_imports() -> None:
    leaked = {"Dict", "List", "Optional", "Tuple", "Union"} & _typing_imports(
        "src/core/agents/corrective_rag_agent.py"
    )
    assert not leaked, f"Legacy typing imports found: {leaked}"


# ---------------------------------------------------------------------------
# als/models/immune_antibody.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_immune_antibody_optional_import_removed() -> None:
    leaked = {"Optional"} & _typing_imports("src/core/als/models/immune_antibody.py")
    assert not leaked


@pytest.mark.unit
def test_immune_antibody_validator_annotations() -> None:
    src = _source("src/core/als/models/immune_antibody.py")
    tree = ast.parse(src)
    found: dict[str, tuple[str | None, str | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "validate_tenant_id",
            "validate_effectiveness",
            "validate_action_type",
        ):
            args = node.args.args
            val_arg = next((a for a in args if a.arg not in ("self", "key")), None)
            param_ann = ast.unparse(val_arg.annotation) if val_arg and val_arg.annotation else None
            ret_ann = ast.unparse(node.returns) if node.returns else None
            found[node.name] = (param_ann, ret_ann)
    assert found.get("validate_tenant_id") == ("int", "int"), (
        f"validate_tenant_id: {found.get('validate_tenant_id')}"
    )
    assert found.get("validate_effectiveness") == ("float", "float"), (
        f"validate_effectiveness: {found.get('validate_effectiveness')}"
    )
    assert found.get("validate_action_type") == ("str", "str"), (
        f"validate_action_type: {found.get('validate_action_type')}"
    )


# ---------------------------------------------------------------------------
# agents/mixins/critic_mixin.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_critic_mixin_legacy_imports_removed() -> None:
    leaked = {"Dict", "Optional"} & _typing_imports("src/core/agents/mixins/critic_mixin.py")
    assert not leaked, f"Legacy imports: {leaked}"


@pytest.mark.unit
def test_critic_mixin_store_critique_uses_critique_type() -> None:
    src = _source("src/core/agents/mixins/critic_mixin.py")
    assert "critique: Critique" in src
    assert "critique: Any" not in src


# ---------------------------------------------------------------------------
# agents/ultimate_cva/tools.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ultimate_cva_tools_optional_removed() -> None:
    leaked = {"Optional"} & _typing_imports("src/core/agents/ultimate_cva/tools.py")
    assert not leaked


@pytest.mark.unit
def test_workflow_node_config_type() -> None:
    src = _source("src/core/agents/ultimate_cva/tools.py")
    assert "config: dict[str, object]" in src
    assert "serialized_results: list[dict[str, object]] = []" in src


# ---------------------------------------------------------------------------
# agents/capabilities/schemas.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_schemas_optional_import_removed() -> None:
    leaked = {"Optional"} & _typing_imports("src/core/agents/capabilities/schemas.py")
    assert not leaked


@pytest.mark.unit
def test_schemas_datetime_types() -> None:
    src = _source("src/core/agents/capabilities/schemas.py")
    assert "from datetime import datetime" in src
    assert "submitted_at: datetime\n" in src
    assert "registered_at: datetime\n" in src
    assert "updated_at: datetime\n" in src


# ---------------------------------------------------------------------------
# als/supervisors/finance_supervisor.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_finance_supervisor_legacy_imports_removed() -> None:
    leaked = {"Dict", "List"} & _typing_imports("src/core/als/supervisors/finance_supervisor.py")
    assert not leaked


@pytest.mark.unit
def test_finance_supervisor_require_tenant_id_type() -> None:
    src = _source("src/core/als/supervisors/finance_supervisor.py")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_require_tenant_id":
            args = node.args.args
            param = next((a for a in args if a.arg == "tenant_id"), None)
            assert param is not None
            assert param.annotation is not None
            ann_str = ast.unparse(param.annotation)
            assert ann_str == "object", f"Expected object, got {ann_str}"
            ret = ast.unparse(node.returns) if node.returns else None
            assert ret == "str", f"Expected str return, got {ret}"
            return
    pytest.fail("_require_tenant_id not found")


# ---------------------------------------------------------------------------
# agents/unified_gateway.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unified_gateway_legacy_imports_removed() -> None:
    leaked = {"Dict", "Optional"} & _typing_imports("src/core/agents/unified_gateway.py")
    assert not leaked


@pytest.mark.unit
def test_unified_gateway_executor_type() -> None:
    src = _source("src/core/agents/unified_gateway.py")
    assert "executor: Callable[[TaskData], ExecutionResult]" in src
    assert "executor: Callable[[TaskData], Any]" not in src


@pytest.mark.unit
def test_unified_gateway_protected_execute_return_type() -> None:
    src = _source("src/core/agents/unified_gateway.py")
    assert "async def protected_execute() -> ExecutionResult:" in src


# ---------------------------------------------------------------------------
# agents/mixins/learning_mixin.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_learning_mixin_normalize_flag_uses_object() -> None:
    src = _source("src/core/agents/mixins/learning_mixin.py")
    assert "_normalize_learning_flag_part(value: object) -> str" in src


@pytest.mark.unit
def test_learning_mixin_property_return_types() -> None:
    src = _source("src/core/agents/mixins/learning_mixin.py")
    assert '"ObservationService | None"' in src or "ObservationService | None" in src
    assert '"AdaptationService | None"' in src or "AdaptationService | None" in src


# ---------------------------------------------------------------------------
# agents/master_orchestrator_agent.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_master_orchestrator_legacy_imports_removed() -> None:
    leaked = {"Dict", "List", "Optional", "Tuple"} & _typing_imports(
        "src/core/agents/master_orchestrator_agent.py"
    )
    assert not leaked, f"Legacy imports: {leaked}"


@pytest.mark.unit
def test_master_orchestrator_metrics_return_type() -> None:
    src = _source("src/core/agents/master_orchestrator_agent.py")
    assert "def metrics(self) -> dict[str, object]:" in src


# ---------------------------------------------------------------------------
# als/models/organism_registry.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_organism_registry_optional_removed() -> None:
    leaked = {"Optional"} & _typing_imports("src/core/als/models/organism_registry.py")
    assert not leaked


@pytest.mark.unit
def test_organism_registry_validator_types() -> None:
    src = _source("src/core/als/models/organism_registry.py")
    tree = ast.parse(src)
    found: dict[str, tuple[str | None, str | None]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "validate_tenant_id",
            "validate_status",
        ):
            args = node.args.args
            val_arg = next((a for a in args if a.arg not in ("self", "key")), None)
            param_ann = ast.unparse(val_arg.annotation) if val_arg and val_arg.annotation else None
            ret_ann = ast.unparse(node.returns) if node.returns else None
            found[node.name] = (param_ann, ret_ann)
    assert found.get("validate_tenant_id") == ("int", "int"), (
        f"validate_tenant_id: {found.get('validate_tenant_id')}"
    )
    assert found.get("validate_status") == ("str", "str"), (
        f"validate_status: {found.get('validate_status')}"
    )


# ---------------------------------------------------------------------------
# als/supervisors/base_supervisor.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_base_supervisor_legacy_imports_removed() -> None:
    leaked = {"Dict", "List"} & _typing_imports("src/core/als/supervisors/base_supervisor.py")
    assert not leaked


@pytest.mark.unit
def test_base_supervisor_concrete_types() -> None:
    src = _source("src/core/als/supervisors/base_supervisor.py")
    assert "selected: list[str] = []" in src
    assert "combined_output: dict[str, object] = {}" in src
