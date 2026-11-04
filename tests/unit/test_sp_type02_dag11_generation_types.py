"""
SP-TYPE-02 Dag 11 -- Type annotation regression tests for generation module.

Verifies that:
- PromptBuilder.strategy_handlers uses Callable[[str, PromptContext], str] (not Callable[..., Any])
- PromptBuilder.optimization_rules uses Callable[[str], tuple[str, list[str]]] (not Callable[..., Any])
- PromptBuildResult.variables_used uses dict[str, str | int | float | bool | None] (not Any)
- PromptBuilder.get_stats() returns PromptBuilderStats TypedDict (not dict[str, Any])
- TemplateEngine.get_template_stats() returns TemplateEngineStats TypedDict (not dict[str, Any])
- TemplateRenderer._parse_function_args returns list[str | int | float | bool] (not list[Any])
"""

import ast
import pathlib
import typing

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


def _source(rel_path: str) -> str:
    """Return source text of a file relative to repo root."""
    return (_REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _ast_tree(rel_path: str) -> ast.Module:
    return ast.parse(_source(rel_path))


def _get_annotation_str(node: ast.expr) -> str:
    """Return the unparsed string of an annotation node."""
    return ast.unparse(node)


# ---------------------------------------------------------------------------
# prompt_builder.py tests
# ---------------------------------------------------------------------------

_PB_PATH = "src/core/generation/prompt_builder.py"


@pytest.mark.unit
def test_prompt_builder_stats_typeddict_defined() -> None:
    """PromptBuilderStats TypedDict must be defined in the module."""
    src = _source(_PB_PATH)
    assert "class PromptBuilderStats(TypedDict):" in src, (
        "PromptBuilderStats TypedDict not found in prompt_builder.py"
    )


@pytest.mark.unit
def test_prompt_builder_stats_typeddict_has_required_keys() -> None:
    """PromptBuilderStats must declare all 6 statistics keys."""
    tree = _ast_tree(_PB_PATH)
    stats_class: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PromptBuilderStats":
            stats_class = node
            break
    assert stats_class is not None, "PromptBuilderStats class not found"

    annotated_keys = {
        stmt.target.id  # type: ignore[attr-defined]
        for stmt in stats_class.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    }
    required = {
        "prompts_built",
        "cache_hits",
        "cache_misses",
        "template_uses",
        "strategy_uses",
        "average_quality_score",
    }
    assert required.issubset(annotated_keys), (
        f"PromptBuilderStats missing keys: {required - annotated_keys}"
    )


@pytest.mark.unit
def test_prompt_build_result_variables_used_not_any() -> None:
    """PromptBuildResult.variables_used must not be annotated as dict[str, Any]."""
    tree = _ast_tree(_PB_PATH)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PromptBuildResult":
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                    and stmt.target.id == "variables_used"
                ):
                    annotation = _get_annotation_str(stmt.annotation)
                    assert "Any" not in annotation, f"variables_used still uses Any: {annotation}"
                    # Must be a union type with concrete scalar types
                    assert "str" in annotation, (
                        f"variables_used missing str in annotation: {annotation}"
                    )
                    return
    pytest.fail("PromptBuildResult.variables_used annotation not found")


@pytest.mark.unit
def test_strategy_handlers_annotation_not_callable_any() -> None:
    """strategy_handlers must not use Callable[..., Any] -- requires concrete signature."""
    src = _source(_PB_PATH)
    # The old form was: dict[PromptStrategy, Callable[..., Any]]
    assert "Callable[..., Any]" not in src or _count_callable_any_in_strategy_handlers(src) == 0, (
        "strategy_handlers still uses Callable[..., Any]"
    )
    assert "Callable[[str, PromptContext], str]" in src, (
        "strategy_handlers must use Callable[[str, PromptContext], str]"
    )


def _count_callable_any_in_strategy_handlers(src: str) -> int:
    """Count Callable[..., Any] occurrences near strategy_handlers assignment."""
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if "strategy_handlers" in line and "Callable[..., Any]" in line:
            return 1
    return 0


@pytest.mark.unit
def test_optimization_rules_annotation_not_callable_any() -> None:
    """optimization_rules must use Callable[[str], tuple[str, list[str]]] (not Callable[..., Any])."""
    src = _source(_PB_PATH)
    assert "Callable[[str], tuple[str, list[str]]]" in src, (
        "optimization_rules must use Callable[[str], tuple[str, list[str]]]"
    )


@pytest.mark.unit
def test_get_stats_return_type_is_typeddict() -> None:
    """PromptBuilder.get_stats() must return PromptBuilderStats, not dict[str, Any]."""
    tree = _ast_tree(_PB_PATH)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PromptBuilder":
            for item in ast.walk(node):
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name == "get_stats"
                    and item.returns is not None
                ):
                    ret = _get_annotation_str(item.returns)
                    assert ret == "PromptBuilderStats", (
                        f"get_stats() return type must be PromptBuilderStats, got: {ret}"
                    )
                    return
    pytest.fail("PromptBuilder.get_stats return annotation not found")


# ---------------------------------------------------------------------------
# template_engine.py tests
# ---------------------------------------------------------------------------

_TE_PATH = "src/core/generation/template_engine.py"


@pytest.mark.unit
def test_template_engine_stats_typeddict_defined() -> None:
    """TemplateEngineStats TypedDict must be defined in template_engine.py."""
    src = _source(_TE_PATH)
    assert "class TemplateEngineStats(TypedDict):" in src, (
        "TemplateEngineStats TypedDict not found in template_engine.py"
    )


@pytest.mark.unit
def test_template_engine_stats_typeddict_has_required_keys() -> None:
    """TemplateEngineStats must declare all 5 statistics keys."""
    tree = _ast_tree(_TE_PATH)
    stats_class: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TemplateEngineStats":
            stats_class = node
            break
    assert stats_class is not None, "TemplateEngineStats class not found"

    annotated_keys = {
        stmt.target.id  # type: ignore[attr-defined]
        for stmt in stats_class.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    }
    required = {
        "templates_loaded",
        "renders_performed",
        "render_errors",
        "available_templates",
        "render_success_rate",
    }
    assert required.issubset(annotated_keys), (
        f"TemplateEngineStats missing keys: {required - annotated_keys}"
    )


@pytest.mark.unit
def test_get_template_stats_return_type_is_typeddict() -> None:
    """TemplateEngine.get_template_stats() must return TemplateEngineStats, not dict[str, Any]."""
    tree = _ast_tree(_TE_PATH)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TemplateEngine":
            for item in ast.walk(node):
                if (
                    isinstance(item, ast.AsyncFunctionDef)
                    and item.name == "get_template_stats"
                    and item.returns is not None
                ):
                    ret = _get_annotation_str(item.returns)
                    assert ret == "TemplateEngineStats", (
                        f"get_template_stats() return type must be TemplateEngineStats, got: {ret}"
                    )
                    return
    pytest.fail("TemplateEngine.get_template_stats return annotation not found")


@pytest.mark.unit
def test_parse_function_args_return_not_list_any() -> None:
    """TemplateRenderer._parse_function_args must return list[str | int | float | bool]."""
    tree = _ast_tree(_TE_PATH)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TemplateRenderer":
            for item in ast.walk(node):
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name == "_parse_function_args"
                    and item.returns is not None
                ):
                    ret = _get_annotation_str(item.returns)
                    assert "Any" not in ret, f"_parse_function_args still returns list[Any]: {ret}"
                    assert "str" in ret and "int" in ret and "float" in ret and "bool" in ret, (
                        f"_parse_function_args return must include str|int|float|bool, got: {ret}"
                    )
                    return
    pytest.fail("TemplateRenderer._parse_function_args return annotation not found")


# ---------------------------------------------------------------------------
# Importability smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_prompt_builder_module_importable() -> None:
    """prompt_builder.py must be importable without errors."""
    import importlib

    mod = importlib.import_module("src.core.generation.prompt_builder")
    assert hasattr(mod, "PromptBuilder")
    assert hasattr(mod, "PromptBuilderStats")


@pytest.mark.unit
def test_template_engine_module_importable() -> None:
    """template_engine.py must be importable without errors."""
    import importlib

    mod = importlib.import_module("src.core.generation.template_engine")
    assert hasattr(mod, "TemplateEngine")
    assert hasattr(mod, "TemplateEngineStats")


@pytest.mark.unit
def test_prompt_builder_stats_typeddict_is_typeddict() -> None:
    """PromptBuilderStats must be a TypedDict at runtime."""
    from src.core.generation.prompt_builder import PromptBuilderStats

    # TypedDicts have __annotations__ and __required_keys__
    assert hasattr(PromptBuilderStats, "__annotations__")
    assert "prompts_built" in PromptBuilderStats.__annotations__


@pytest.mark.unit
def test_template_engine_stats_typeddict_is_typeddict() -> None:
    """TemplateEngineStats must be a TypedDict at runtime."""
    from src.core.generation.template_engine import TemplateEngineStats

    assert hasattr(TemplateEngineStats, "__annotations__")
    assert "templates_loaded" in TemplateEngineStats.__annotations__
