"""SP-TYPE Batch A -- AST regression tests for type-annotation hardening.

Covers:
- unified_config.py: TypedDict classes + narrowed validator/method signatures
- audit_logger.py: TODO(TYPE) markers on all Any annotations
- master_orchestrator_agent.py: AgentRouterAgent/ParallelExecutor annotations
- corrective_rag_agent.py: TODO(TYPE) markers on Any annotations
- prompt_builder.py: PromptBuilderStats TypedDict + concrete Callable signatures
- template_engine.py: TemplateEngineStats TypedDict + list[str|int|float|bool]
- als/router.py: AsyncRedisClient + AgentRegistration concrete types
- workflow/providers.py: AsyncSession + SubagentLoader + AgentDefinition types
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _ast_tree(rel: str) -> ast.Module:
    src = _source(rel)
    return ast.parse(src, filename=rel)


# ---------------------------------------------------------------------------
# unified_config.py
# ---------------------------------------------------------------------------

_UC = "src/core/config/unified_config.py"


@pytest.mark.unit
def test_unified_config_typeddict_import() -> None:
    assert "TypedDict" in _source(_UC), "TypedDict must be imported in unified_config.py"


@pytest.mark.unit
def test_unified_config_typeddict_classes_defined() -> None:
    src = _source(_UC)
    for name in [
        "class CorsConfig",
        "class DatabaseConfig",
        "class RedisConfig",
        "class LlmConfig",
        "class AgentConfig",
        "class SecurityConfig",
        "class HttpsConfig",
        "class SecurityHeadersConfig",
    ]:
        assert name in src, f"Expected TypedDict class not found: {name}"


@pytest.mark.unit
def test_unified_config_validate_cors_origins_returns_list_str() -> None:
    src = _source(_UC)
    after = src.split("def validate_cors_origins")[1].split("def ")[0]
    assert "-> Any" not in after, "validate_cors_origins still has -> Any return annotation"
    assert "list[str]" in after, "validate_cors_origins missing list[str] return annotation"


@pytest.mark.unit
def test_unified_config_get_config_methods_return_typeddict() -> None:
    src = _source(_UC)
    checks = [
        ("get_cors_config", "CorsConfig"),
        ("get_database_config", "DatabaseConfig"),
        ("get_redis_config", "RedisConfig"),
        ("get_llm_config", "LlmConfig"),
        ("get_agent_config", "AgentConfig"),
        ("get_security_config", "SecurityConfig"),
        ("get_https_config", "HttpsConfig"),
        ("get_security_headers_config", "SecurityHeadersConfig"),
    ]
    for method, return_type in checks:
        parts = src.split(f"def {method}")
        assert len(parts) > 1, f"{method} not found in unified_config.py"
        method_src = parts[1].split("def ")[0]
        assert return_type in method_src, f"{method} missing {return_type} return annotation"
        # Ensure the return annotation line does not say dict[str, Any]
        sig_part = method_src.split(":")[0]
        assert "dict[str, Any]" not in sig_part, (
            f"{method} still has dict[str, Any] return annotation"
        )


@pytest.mark.unit
def test_unified_config_inject_secrets_uses_str_str() -> None:
    src = _source(_UC)
    assert "dict[str, str]" in src, "_inject_secrets_from_manager should use dict[str, str]"


@pytest.mark.unit
def test_unified_config_docstring_tuple_updated() -> None:
    src = _source(_UC)
    assert "Tuple[Any, ...]" not in src, "Docstring still references deprecated Tuple[Any, ...]"


# ---------------------------------------------------------------------------
# audit_logger.py
# ---------------------------------------------------------------------------

_AL = "src/core/observability/audit_logger.py"


@pytest.mark.unit
def test_audit_logger_redact_has_todo_markers() -> None:
    src = _source(_AL)
    assert "TODO(TYPE)" in src, "audit_logger.py must have at least one TODO(TYPE) marker"


@pytest.mark.unit
def test_audit_logger_any_lines_have_todo_markers() -> None:
    src = _source(_AL)
    violations: list[str] = []
    for i, line in enumerate(src.splitlines(), start=1):
        stripped = line.strip()
        if (
            stripped.startswith("#")
            or stripped.startswith("from ")
            or stripped.startswith("import ")
        ):
            continue
        has_any = bool(re.search(r":\s*Any\b", line) or re.search(r"->\s*Any\b", line))
        has_todo = "TODO(TYPE)" in line
        if has_any and not has_todo:
            violations.append(f"  line {i}: {line.rstrip()}")
    assert not violations, "Lines with Any annotation missing TODO(TYPE) marker:\n" + "\n".join(
        violations
    )


# ---------------------------------------------------------------------------
# master_orchestrator_agent.py
# ---------------------------------------------------------------------------

_MO = "src/core/agents/master_orchestrator_agent.py"


@pytest.mark.unit
def test_master_orchestrator_type_checking_imported() -> None:
    src = _source(_MO)
    assert "TYPE_CHECKING" in src, "TYPE_CHECKING must be imported"
    assert "AgentRouterAgent" in src, "AgentRouterAgent not referenced"
    assert "ParallelExecutor" in src, "ParallelExecutor not referenced"


@pytest.mark.unit
def test_master_orchestrator_router_annotation() -> None:
    src = _source(_MO)
    assert "AgentRouterAgent | None" in src, "_router must be annotated AgentRouterAgent | None"


@pytest.mark.unit
def test_master_orchestrator_executor_annotation() -> None:
    src = _source(_MO)
    assert "ParallelExecutor | None" in src, "_executor must be annotated ParallelExecutor | None"


@pytest.mark.unit
def test_master_orchestrator_get_router_return_type() -> None:
    tree = _ast_tree(_MO)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_get_router":
            assert node.returns is not None, "_get_router has no return annotation"
            annotation = ast.unparse(node.returns)
            assert annotation == "AgentRouterAgent", (
                f"_get_router return annotation is '{annotation}', expected 'AgentRouterAgent'"
            )
            return
    pytest.fail("_get_router not found")


@pytest.mark.unit
def test_master_orchestrator_critic_field_removed() -> None:
    """SP-WE-11: self._critic = None (object|None) was removed.
    CriticMixin.post_process_task() is used instead -- no direct _critic field needed.
    Replaces the old TODO(TYPE) check that tracked the untyped field.
    """
    src = _source(_MO)
    # The object|None = None field must be gone; CriticMixin handles critic lazily
    old_pattern_lines = [
        line
        for line in src.splitlines()
        if "self._critic" in line and "object" in line and "None" in line
    ]
    assert old_pattern_lines == [], (
        "self._critic: object | None field must be removed (SP-WE-11). "
        "Use CriticMixin.post_process_task() instead."
    )


# ---------------------------------------------------------------------------
# corrective_rag_agent.py
# ---------------------------------------------------------------------------

_CR = "src/core/agents/corrective_rag_agent.py"


@pytest.mark.unit
def test_corrective_rag_any_annotations_have_todo_markers() -> None:
    src = _source(_CR)
    # Skip lines inside known generic-proxy methods (__call__, __getattr__, __class__)
    generic_proxy_methods = {"__call__", "__getattr__", "__class__"}
    violations: list[str] = []
    all_lines = src.splitlines()
    for i, line in enumerate(all_lines, start=1):
        stripped = line.strip()
        if (
            stripped.startswith("#")
            or stripped.startswith("from ")
            or stripped.startswith("import ")
        ):
            continue
        if any(m in line for m in generic_proxy_methods):
            continue
        has_any = bool(re.search(r":\s*Any\b", line) or re.search(r"->\s*Any\b", line))
        # Accept TODO on the annotation line OR on the immediately following line
        # (formatter may wrap long annotation+comment combos)
        next_line = all_lines[i] if i < len(all_lines) else ""
        has_todo = "TODO(TYPE)" in line or "TODO(TYPE)" in next_line
        if has_any and not has_todo:
            violations.append(f"  line {i}: {line.rstrip()}")
    assert not violations, "Lines with Any annotation missing TODO(TYPE) marker:\n" + "\n".join(
        violations
    )


# ---------------------------------------------------------------------------
# prompt_builder.py
# ---------------------------------------------------------------------------

_PB = "src/core/generation/prompt_builder.py"


@pytest.mark.unit
def test_prompt_builder_stats_typeddict_defined() -> None:
    assert "class PromptBuilderStats(TypedDict):" in _source(_PB)


@pytest.mark.unit
def test_prompt_builder_stats_has_required_keys() -> None:
    tree = _ast_tree(_PB)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PromptBuilderStats":
            ann_names = {
                n.target.id
                for n in ast.walk(node)
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
            }
            for key in [
                "prompts_built",
                "cache_hits",
                "cache_misses",
                "template_uses",
                "strategy_uses",
                "average_quality_score",
            ]:
                assert key in ann_names, f"PromptBuilderStats missing key: {key}"
            return
    pytest.fail("PromptBuilderStats class not found")


@pytest.mark.unit
def test_prompt_builder_variables_used_not_any() -> None:
    tree = _ast_tree(_PB)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PromptBuildResult":
            for item in ast.walk(node):
                if (
                    isinstance(item, ast.AnnAssign)
                    and isinstance(item.target, ast.Name)
                    and item.target.id == "variables_used"
                ):
                    ann = ast.unparse(item.annotation)
                    assert "Any" not in ann, f"variables_used annotation contains Any: {ann}"
                    return
    pytest.fail("variables_used field not found in PromptBuildResult")


@pytest.mark.unit
def test_prompt_builder_strategy_handlers_concrete_callable() -> None:
    assert "Callable[[str, PromptContext], str]" in _source(_PB)


@pytest.mark.unit
def test_prompt_builder_optimization_rules_concrete_callable() -> None:
    assert "Callable[[str], tuple[str, list[str]]]" in _source(_PB)


@pytest.mark.unit
def test_prompt_builder_get_stats_returns_typeddict() -> None:
    tree = _ast_tree(_PB)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PromptBuilder":
            for item in ast.walk(node):
                if isinstance(item, ast.FunctionDef) and item.name == "get_stats" and item.returns:
                    assert ast.unparse(item.returns) == "PromptBuilderStats"
                    return
    pytest.fail("get_stats not found in PromptBuilder")


@pytest.mark.unit
def test_prompt_builder_module_importable() -> None:
    mod = importlib.import_module("src.core.generation.prompt_builder")
    assert hasattr(mod, "PromptBuilderStats")


@pytest.mark.unit
def test_prompt_builder_stats_is_typeddict_at_runtime() -> None:
    from src.core.generation.prompt_builder import PromptBuilderStats

    assert "prompts_built" in PromptBuilderStats.__annotations__


# ---------------------------------------------------------------------------
# template_engine.py
# ---------------------------------------------------------------------------

_TE = "src/core/generation/template_engine.py"


@pytest.mark.unit
def test_template_engine_stats_typeddict_defined() -> None:
    assert "class TemplateEngineStats(TypedDict):" in _source(_TE)


@pytest.mark.unit
def test_template_engine_stats_has_required_keys() -> None:
    tree = _ast_tree(_TE)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TemplateEngineStats":
            ann_names = {
                n.target.id
                for n in ast.walk(node)
                if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
            }
            for key in [
                "templates_loaded",
                "renders_performed",
                "render_errors",
                "available_templates",
                "render_success_rate",
            ]:
                assert key in ann_names, f"TemplateEngineStats missing key: {key}"
            return
    pytest.fail("TemplateEngineStats class not found")


@pytest.mark.unit
def test_template_engine_parse_function_args_not_list_any() -> None:
    tree = _ast_tree(_TE)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TemplateRenderer":
            for item in ast.walk(node):
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name == "_parse_function_args"
                    and item.returns
                ):
                    ret = ast.unparse(item.returns)
                    assert "Any" not in ret, f"_parse_function_args return contains Any: {ret}"
                    assert "str" in ret and "int" in ret and "float" in ret and "bool" in ret
                    return
    pytest.fail("_parse_function_args not found in TemplateRenderer")


@pytest.mark.unit
def test_template_engine_get_template_stats_returns_typeddict() -> None:
    tree = _ast_tree(_TE)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TemplateEngine":
            for item in ast.walk(node):
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == "get_template_stats"
                    and item.returns
                ):
                    assert ast.unparse(item.returns) == "TemplateEngineStats"
                    return
    pytest.fail("get_template_stats not found in TemplateEngine")


@pytest.mark.unit
def test_template_engine_module_importable() -> None:
    mod = importlib.import_module("src.core.generation.template_engine")
    assert hasattr(mod, "TemplateEngineStats")


@pytest.mark.unit
def test_template_engine_stats_is_typeddict_at_runtime() -> None:
    from src.core.generation.template_engine import TemplateEngineStats

    assert "templates_loaded" in TemplateEngineStats.__annotations__


# ---------------------------------------------------------------------------
# als/router.py
# ---------------------------------------------------------------------------

_AR = "src/core/als/router.py"


@pytest.mark.unit
def test_als_router_async_redis_client_imported() -> None:
    src = _source(_AR)
    assert "AsyncRedisClient" in src, "AsyncRedisClient must be imported in router.py"


@pytest.mark.unit
def test_als_router_agent_registration_imported() -> None:
    src = _source(_AR)
    assert "AgentRegistration" in src, "AgentRegistration must be imported in router.py"
    assert "OrganismRegistry" in src, "OrganismRegistry must be imported in router.py"


@pytest.mark.unit
def test_als_router_filter_healthy_agents_typed() -> None:
    src = _source(_AR)
    assert "list[AgentRegistration]" in src, "list[AgentRegistration] not found in router.py"


@pytest.mark.unit
def test_als_router_best_tuple_typed() -> None:
    src = _source(_AR)
    assert "tuple[float, AgentRegistration]" in src, "best tuple not narrowed to AgentRegistration"


@pytest.mark.unit
def test_als_router_get_router_redis_typed() -> None:
    src = _source(_AR)
    # get_router function should use AsyncRedisClient, not Any
    func_parts = src.split("async def get_router(")
    assert len(func_parts) > 1, "get_router not found"
    sig = func_parts[1].split(") -> RouterService:")[0]
    assert "AsyncRedisClient" in sig, "get_router redis_client not typed as AsyncRedisClient"


@pytest.mark.unit
def test_als_router_get_router_registry_typed() -> None:
    src = _source(_AR)
    func_parts = src.split("async def get_router(")
    assert len(func_parts) > 1, "get_router not found"
    sig = func_parts[1].split(") -> RouterService:")[0]
    assert "OrganismRegistry" in sig, "get_router registry not typed as OrganismRegistry"


# ---------------------------------------------------------------------------
# workflow/providers.py
# ---------------------------------------------------------------------------

_WP = "src/core/workflow/providers.py"


@pytest.mark.unit
def test_workflow_providers_type_checking_imported() -> None:
    assert "TYPE_CHECKING" in _source(_WP)


@pytest.mark.unit
def test_workflow_providers_subagent_loader_typed() -> None:
    src = _source(_WP)
    assert "SubagentLoader | None" in src, "subagent_loader must be SubagentLoader | None"


@pytest.mark.unit
def test_workflow_providers_agent_definition_typed() -> None:
    src = _source(_WP)
    assert "AgentDefinition" in src, "AgentDefinition not referenced in providers.py"


@pytest.mark.unit
def test_workflow_providers_async_session_maker_typed() -> None:
    src = _source(_WP)
    assert "async_sessionmaker[AsyncSession]" in src, "async_sessionmaker[AsyncSession] not found"


@pytest.mark.unit
def test_workflow_providers_session_property_typed() -> None:
    src = _source(_WP)
    # ProductionUnitOfWork.session property should return AsyncSession
    assert "-> AsyncSession:" in src, "session property not returning AsyncSession"


@pytest.mark.unit
def test_workflow_providers_session_attr_typed() -> None:
    src = _source(_WP)
    assert "AsyncSession | None" in src, "_session attribute not typed as AsyncSession | None"
