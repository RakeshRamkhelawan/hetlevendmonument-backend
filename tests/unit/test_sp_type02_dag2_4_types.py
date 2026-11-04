"""
SP-TYPE-01 Dag 2-4: AST-based annotation verification tests.
Verifies that list[Any] / Any annotations were replaced with concrete types.
"""

from __future__ import annotations

import ast
import pathlib

import pytest


def _fn_return_ann(filepath: str, fn_name: str) -> str:
    source = pathlib.Path(filepath).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            if node.returns:
                return ast.unparse(node.returns)
    return ""


def _param_ann(filepath: str, fn_name: str, param: str) -> str:
    source = pathlib.Path(filepath).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            for arg in node.args.args:
                if arg.arg == param:
                    return ast.unparse(arg.annotation) if arg.annotation else ""
    return ""


def _local_ann(filepath: str, fn_name: str, var_name: str) -> str:
    source = pathlib.Path(filepath).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.AnnAssign):
                    if isinstance(stmt.target, ast.Name) and stmt.target.id == var_name:
                        return ast.unparse(stmt.annotation)
    return ""


# ---------------------------------------------------------------------------
# llm_client.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_formatted_messages_is_list_llmmessage():
    fp = "src/core/llm/llm_client.py"
    ann = _local_ann(fp, "generate_response", "formatted_messages")
    assert ann == "list[LLMMessage]", f"Expected list[LLMMessage], got {ann!r}"


@pytest.mark.unit
def test_user_messages_is_list_dict_str_str():
    fp = "src/core/llm/llm_client.py"
    ann = _local_ann(fp, "chat_completion", "user_messages")
    assert "dict[str, str]" in ann, f"Expected dict[str, str] in annotation, got {ann!r}"


@pytest.mark.unit
def test_prompt_parts_is_list_str():
    fp = "src/core/llm/llm_client.py"
    ann = _local_ann(fp, "chat_completion", "prompt_parts")
    assert ann == "list[str]", f"Expected list[str], got {ann!r}"


@pytest.mark.unit
def test_aexit_exc_type_annotation():
    fp = "src/core/llm/llm_client.py"
    source = pathlib.Path(fp).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "__aexit__":
            for arg in node.args.args:
                if arg.arg == "exc_type":
                    ann = ast.unparse(arg.annotation) if arg.annotation else ""
                    assert "BaseException" in ann, (
                        f"Expected BaseException in exc_type annotation, got {ann!r}"
                    )
                    return
    assert False, "__aexit__ not found in llm_client.py"


# ---------------------------------------------------------------------------
# gemini_provider.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gemini_models_is_list_str():
    fp = "src/core/llm/gemini_provider.py"
    ann = _local_ann(fp, "_discover_available_models", "gemini_models")
    assert ann == "list[str]", f"Expected list[str], got {ann!r}"


@pytest.mark.unit
def test_function_calls_is_list_dict():
    fp = "src/core/llm/gemini_provider.py"
    ann = _local_ann(fp, "generate_response", "function_calls")
    assert "dict[str, Any]" in ann or "dict[str, object]" in ann, f"Expected list[dict[str, Any or object]], got {ann!r}"


# ---------------------------------------------------------------------------
# ollama_provider.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parsed_function_calls_is_list_dict():
    fp = "src/core/llm/ollama_provider.py"
    ann = _local_ann(fp, "generate_response", "parsed_function_calls")
    assert "dict[str, Any]" in ann or "dict[str, object]" in ann, f"Expected list[dict[str, Any or object]], got {ann!r}"


@pytest.mark.unit
def test_formatted_is_list_dict():
    fp = "src/core/llm/ollama_provider.py"
    ann = _local_ann(fp, "_format_tools_for_ollama", "formatted")
    assert "dict[str, Any]" in ann or "dict[str, object]" in ann, f"Expected list[dict[str, Any or object]], got {ann!r}"


# ---------------------------------------------------------------------------
# mock_provider.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_complete_json_messages_not_any():
    fp = "src/core/llm/mock_provider.py"
    ann = _param_ann(fp, "complete_json", "messages")
    assert ann != "Any", f"Expected concrete type, still Any: {ann!r}"
    assert "LLMMessage" in ann, f"Expected LLMMessage in annotation, got {ann!r}"


# ---------------------------------------------------------------------------
# factory.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_redis_safe_return_not_any():
    fp = "src/core/copilot/council/factory.py"
    ann = _fn_return_ann(fp, "_get_redis_safe")
    assert ann != "Any", f"Expected concrete return type, still Any: {ann!r}"
    assert "None" in ann, f"Expected Optional-style return, got {ann!r}"


@pytest.mark.unit
def test_create_twin_service_redis_param_not_any():
    fp = "src/core/copilot/council/factory.py"
    ann = _param_ann(fp, "_create_twin_service", "redis")
    assert ann != "Any", f"Expected concrete type for redis param, still Any: {ann!r}"


@pytest.mark.unit
def test_assess_proposal_param_not_any():
    fp = "src/core/copilot/council/factory.py"
    ann = _param_ann(fp, "assess", "proposal")
    assert ann != "Any", f"Expected Proposal type, still Any: {ann!r}"
    assert "Proposal" in ann, f"Expected Proposal in annotation, got {ann!r}"


@pytest.mark.unit
def test_actor_track_record_return_not_any():
    fp = "src/core/copilot/council/factory.py"
    ann = _fn_return_ann(fp, "actor_track_record")
    assert "Any" not in ann, f"Expected no Any in return type, got {ann!r}"
    assert "dict" in ann, f"Expected dict in return type, got {ann!r}"


# ---------------------------------------------------------------------------
# learning/metrics.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_metrics_py_exit_uses_traceback_type():
    src = pathlib.Path("src/core/learning/metrics.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TimedContext":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__exit__":
                    exc_tb_arg = item.args.args[3]
                    assert exc_tb_arg.annotation is not None, "exc_tb must be annotated"
                    annotation_src = ast.unparse(exc_tb_arg.annotation)
                    assert "TracebackType" in annotation_src, (
                        f"exc_tb annotation should contain TracebackType, got: {annotation_src}"
                    )
                    assert "Any" not in annotation_src, (
                        f"exc_tb annotation must not use Any, got: {annotation_src}"
                    )
                    return
    raise AssertionError("TimedContext.__exit__ not found in metrics.py")


# ---------------------------------------------------------------------------
# auto_learning.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_auto_learning_py_no_legacy_typing_imports():
    src = pathlib.Path("src/core/learning/auto_learning.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            names = [alias.name for alias in node.names]
            assert "Optional" not in names, (
                "Optional should be removed from typing imports in auto_learning.py "
                "(use X | None syntax instead)"
            )
            assert "Dict" not in names, (
                "Dict should be removed from typing imports in auto_learning.py "
                "(use dict[...] syntax instead)"
            )


# ---------------------------------------------------------------------------
# gdpr_service.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gdpr_service_py_no_legacy_optional_import():
    src = pathlib.Path("src/core/learning/gdpr_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            names = [alias.name for alias in node.names]
            assert "Optional" not in names, (
                "Optional should be removed from gdpr_service.py typing imports "
                "(file uses from __future__ import annotations and X | None syntax)"
            )
    assert "# TODO(TYPE)" not in src or all(
        "_serialize_" not in line for line in src.splitlines() if "# TODO(TYPE)" in line
    ), "Stale TODO(TYPE) comments remain on _serialize_* methods"


# ---------------------------------------------------------------------------
# worker.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_worker_py_no_cast_any_pattern():
    src = pathlib.Path("src/core/learning/worker.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            names = [alias.name for alias in node.names]
            assert "Dict" not in names, "Legacy typing.Dict should be removed"
            assert "List" not in names, "Legacy typing.List should be removed"
    found_results_annotation = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "results":
                annotation_src = ast.unparse(node.annotation)
                assert "dict" in annotation_src, (
                    f"results variable should use dict[str, Any], got: {annotation_src}"
                )
                found_results_annotation = True
    assert found_results_annotation, "Annotated results variable not found in worker.py"


# ---------------------------------------------------------------------------
# meta_learning.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_meta_learning_py_all_metrics_typed_as_float():
    src = pathlib.Path("src/core/learning/meta_learning.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MetaLearningManager":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "meta_train_step":
                    for stmt in ast.walk(item):
                        if isinstance(stmt, ast.AnnAssign):
                            if (
                                isinstance(stmt.target, ast.Name)
                                and stmt.target.id == "all_metrics"
                            ):
                                annotation_src = ast.unparse(stmt.annotation)
                                assert "float" in annotation_src, (
                                    f"all_metrics should be dict[str, float], got: {annotation_src}"
                                )
                                assert "Any" not in annotation_src, (
                                    f"all_metrics must not use Any, got: {annotation_src}"
                                )
                                return
    raise AssertionError("all_metrics annotation not found in MetaLearningManager.meta_train_step")


# ---------------------------------------------------------------------------
# observability/metrics.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_metrics_return_types_are_concrete() -> None:
    """AST-based: _get_or_create_* helpers must declare concrete return types, not Any."""
    src = pathlib.Path("src/core/observability/metrics.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    expected: dict[str, str] = {
        "_get_or_create_counter": "Counter",
        "_get_or_create_histogram": "Histogram",
        "_get_or_create_gauge": "Gauge",
    }

    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in expected:
            if node.returns is not None:
                found[node.name] = ast.unparse(node.returns)

    for func_name, expected_return in expected.items():
        assert func_name in found, f"{func_name} not found in AST"
        actual = found[func_name]
        assert actual == expected_return, (
            f"{func_name} return annotation is '{actual}', expected '{expected_return}'"
        )
        assert "Any" not in actual, f"{func_name} still uses Any in return annotation"


# ---------------------------------------------------------------------------
# observability/alert_manager.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_alert_manager_list_annotations_are_concrete() -> None:
    """AST-based: firing/active/history locals must be annotated list[Alert], not list[Any]."""
    src = pathlib.Path("src/core/observability/alert_manager.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    bad_patterns: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            annotation_src = ast.unparse(node.annotation)
            if "list[Any]" in annotation_src:
                target = ast.unparse(node.target) if hasattr(node, "target") else "unknown"
                bad_patterns.append(f"{target}: {annotation_src} (line {node.lineno})")

    assert not bad_patterns, "Found list[Any] annotations that should be list[Alert]: " + ", ".join(
        bad_patterns
    )


# ---------------------------------------------------------------------------
# learning/observability/metrics.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_twin_metrics_annotations_are_concrete() -> None:
    """AST-based: all TWIN_* module-level vars must use Counter/Histogram/Gauge, not Any."""
    src = pathlib.Path("src/core/learning/observability/metrics.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    allowed_metric_types = {"Counter", "Histogram", "Gauge"}
    any_typed: list[str] = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id.startswith("TWIN_")
        ):
            annotation_src = ast.unparse(node.annotation)
            if annotation_src not in allowed_metric_types:
                any_typed.append(f"{node.target.id}: {annotation_src} (line {node.lineno})")

    assert not any_typed, (
        "TWIN_* metrics with non-concrete annotation (expected Counter/Histogram/Gauge): "
        + ", ".join(any_typed)
    )
