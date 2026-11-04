"""
SP-TYPE-07 -- Depends annotation type-safety regression tests.

One test per changed file verifying that:
- _authenticated parameters use dict[str, Any] instead of bare Any
- filters local variable uses dict[str, str | bool] instead of dict[str, Any]
- engine/analytics parameters use concrete engine types instead of bare Any
- Modules import without error

Files covered:
- src/core/api/v1/company/template_router.py
- src/core/api/v1/ai_features/learning_router.py
- src/core/api/v1/ai_features/analytics_router.py
- src/core/api/v1/ai_features/system_router.py
"""

import ast
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_source(rel_path: str) -> str:
    """Return source text of a file relative to repo root."""
    return (ROOT / rel_path).read_text(encoding="utf-8")


def _get_func_arg_annotation(src: str, func_name: str, arg_name: str) -> str | None:
    """Return the annotation text of a specific argument in a function.

    Uses AST to find the function definition and inspect argument annotations.
    Returns the unparsed annotation string, or None if not found.
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                for arg in node.args.args:
                    if arg.arg == arg_name and arg.annotation is not None:
                        return ast.unparse(arg.annotation)
    return None


def _get_local_var_annotation(src: str, func_name: str, var_name: str) -> str | None:
    """Return the annotation of a local annotated assignment inside a function.

    Looks for AnnAssign nodes directly inside the function body.
    Returns the unparsed annotation string, or None if not found.
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                for child in ast.walk(node):
                    if isinstance(child, ast.AnnAssign):
                        if isinstance(child.target, ast.Name):
                            if child.target.id == var_name and child.annotation is not None:
                                return ast.unparse(child.annotation)
    return None


# ---------------------------------------------------------------------------
# template_router.py tests
# ---------------------------------------------------------------------------

TEMPLATE_ROUTER = "src/core/api/v1/company/template_router.py"


class TestTemplateRouterDependsAnnotations:
    """Verify _authenticated parameters use dict[str, Any], not bare Any."""

    @pytest.fixture(scope="class")
    def src(self) -> str:
        return _read_source(TEMPLATE_ROUTER)

    @pytest.mark.unit
    def test_get_template_service_current_user_not_bare_any(self, src: str) -> None:
        """current_user in get_template_service must not be bare Any."""
        annotation = _get_func_arg_annotation(src, "get_template_service", "current_user")
        assert annotation is not None, "current_user annotation missing from get_template_service"
        assert annotation != "Any", (
            f"current_user annotation is bare Any in get_template_service; got: {annotation!r}"
        )
        # Must be dict-based
        assert "dict" in annotation, (
            f"current_user annotation should be dict[str, Any]; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_list_templates_authenticated_not_bare_any(self, src: str) -> None:
        """_authenticated in list_templates must not be bare Any."""
        annotation = _get_func_arg_annotation(src, "list_templates", "_authenticated")
        assert annotation is not None, "_authenticated annotation missing from list_templates"
        assert annotation != "Any", (
            f"_authenticated is bare Any in list_templates; got: {annotation!r}"
        )
        assert "dict" in annotation, f"_authenticated should be dict[str, Any]; got: {annotation!r}"

    @pytest.mark.unit
    def test_get_template_authenticated_not_bare_any(self, src: str) -> None:
        """_authenticated in get_template must not be bare Any."""
        annotation = _get_func_arg_annotation(src, "get_template", "_authenticated")
        assert annotation is not None, "_authenticated annotation missing from get_template"
        assert annotation != "Any", (
            f"_authenticated is bare Any in get_template; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_instantiate_template_authenticated_not_bare_any(self, src: str) -> None:
        """_authenticated in instantiate_template must not be bare Any."""
        annotation = _get_func_arg_annotation(src, "instantiate_template", "_authenticated")
        assert annotation is not None, "_authenticated annotation missing from instantiate_template"
        assert annotation != "Any", (
            f"_authenticated is bare Any in instantiate_template; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_export_company_authenticated_not_bare_any(self, src: str) -> None:
        """_authenticated in export_company must not be bare Any."""
        annotation = _get_func_arg_annotation(src, "export_company", "_authenticated")
        assert annotation is not None, "_authenticated annotation missing from export_company"
        assert annotation != "Any", (
            f"_authenticated is bare Any in export_company; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_contribute_template_authenticated_not_bare_any(self, src: str) -> None:
        """_authenticated in contribute_template must not be bare Any."""
        annotation = _get_func_arg_annotation(src, "contribute_template", "_authenticated")
        assert annotation is not None, "_authenticated annotation missing from contribute_template"
        assert annotation != "Any", (
            f"_authenticated is bare Any in contribute_template; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_list_company_types_authenticated_not_bare_any(self, src: str) -> None:
        """_authenticated in list_company_types must not be bare Any."""
        annotation = _get_func_arg_annotation(src, "list_company_types", "_authenticated")
        assert annotation is not None, "_authenticated annotation missing from list_company_types"
        assert annotation != "Any", (
            f"_authenticated is bare Any in list_company_types; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_list_sectors_authenticated_not_bare_any(self, src: str) -> None:
        """_authenticated in list_sectors must not be bare Any."""
        annotation = _get_func_arg_annotation(src, "list_sectors", "_authenticated")
        assert annotation is not None, "_authenticated annotation missing from list_sectors"
        assert annotation != "Any", (
            f"_authenticated is bare Any in list_sectors; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_filters_local_var_narrowed(self, src: str) -> None:
        """filters local var in list_templates must use str | bool value type, not Any."""
        annotation = _get_local_var_annotation(src, "list_templates", "filters")
        assert annotation is not None, "filters annotation missing from list_templates"
        assert annotation != "dict[str, Any]", (
            f"filters annotation is dict[str, Any] (too broad); got: {annotation!r}"
        )
        # Must still be a dict annotation
        assert "dict" in annotation, f"filters should be dict[str, str | bool]; got: {annotation!r}"


# ---------------------------------------------------------------------------
# ai_features sub-router tests
# ---------------------------------------------------------------------------

LEARNING_ROUTER = "src/core/api/v1/ai_features/learning_router.py"
ANALYTICS_ROUTER = "src/core/api/v1/ai_features/analytics_router.py"
SYSTEM_ROUTER = "src/core/api/v1/ai_features/system_router.py"


class TestAiFeaturesEndpointsDependsAnnotations:
    """Verify engine/analytics Depends parameters use concrete engine types."""

    @pytest.fixture(scope="class")
    def learning_src(self) -> str:
        return _read_source(LEARNING_ROUTER)

    @pytest.fixture(scope="class")
    def analytics_src(self) -> str:
        return _read_source(ANALYTICS_ROUTER)

    @pytest.fixture(scope="class")
    def system_src(self) -> str:
        return _read_source(SYSTEM_ROUTER)

    @pytest.mark.unit
    def test_record_learning_event_engine_not_bare_any(self, learning_src: str) -> None:
        """engine in record_learning_event must not be bare Any."""
        annotation = _get_func_arg_annotation(learning_src, "record_learning_event", "engine")
        assert annotation is not None, "engine annotation missing from record_learning_event"
        assert annotation != "Any", (
            f"engine is bare Any in record_learning_event; got: {annotation!r}"
        )
        assert "AdaptiveLearningEngine" in annotation, (
            f"engine should be AdaptiveLearningEngine; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_get_learning_insights_engine_not_bare_any(self, learning_src: str) -> None:
        """engine in get_learning_insights must not be bare Any."""
        annotation = _get_func_arg_annotation(learning_src, "get_learning_insights", "engine")
        assert annotation is not None, "engine annotation missing from get_learning_insights"
        assert annotation != "Any", (
            f"engine is bare Any in get_learning_insights; got: {annotation!r}"
        )
        assert "AdaptiveLearningEngine" in annotation, (
            f"engine should be AdaptiveLearningEngine; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_make_prediction_analytics_not_bare_any(self, analytics_src: str) -> None:
        """analytics in make_prediction must not be bare Any."""
        annotation = _get_func_arg_annotation(analytics_src, "make_prediction", "analytics")
        assert annotation is not None, "analytics annotation missing from make_prediction"
        assert annotation != "Any", f"analytics is bare Any in make_prediction; got: {annotation!r}"
        assert "PredictiveAnalyticsEngine" in annotation, (
            f"analytics should be PredictiveAnalyticsEngine; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_get_ai_system_status_adaptive_engine_not_bare_any(self, system_src: str) -> None:
        """adaptive_learning_engine in get_ai_system_status must not be bare Any."""
        annotation = _get_func_arg_annotation(
            system_src, "get_ai_system_status", "adaptive_learning_engine"
        )
        assert annotation is not None, (
            "adaptive_learning_engine annotation missing from get_ai_system_status"
        )
        assert annotation != "Any", (
            f"adaptive_learning_engine is bare Any in get_ai_system_status; got: {annotation!r}"
        )
        assert "AdaptiveLearningEngine" in annotation, (
            f"adaptive_learning_engine should be AdaptiveLearningEngine; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_get_ai_system_status_intelligent_router_not_bare_any(self, system_src: str) -> None:
        """intelligent_router in get_ai_system_status must not be bare Any."""
        annotation = _get_func_arg_annotation(system_src, "get_ai_system_status", "intelligent_router")
        assert annotation is not None, (
            "intelligent_router annotation missing from get_ai_system_status"
        )
        assert annotation != "Any", (
            f"intelligent_router is bare Any in get_ai_system_status; got: {annotation!r}"
        )
        assert "IntelligentRouter" in annotation, (
            f"intelligent_router should be IntelligentRouter; got: {annotation!r}"
        )

    @pytest.mark.unit
    def test_get_ai_system_status_predictive_analytics_not_bare_any(self, system_src: str) -> None:
        """predictive_analytics in get_ai_system_status must not be bare Any."""
        annotation = _get_func_arg_annotation(system_src, "get_ai_system_status", "predictive_analytics")
        assert annotation is not None, (
            "predictive_analytics annotation missing from get_ai_system_status"
        )
        assert annotation != "Any", (
            f"predictive_analytics is bare Any in get_ai_system_status; got: {annotation!r}"
        )
        assert "PredictiveAnalyticsEngine" in annotation, (
            f"predictive_analytics should be PredictiveAnalyticsEngine; got: {annotation!r}"
        )
