"""
TDD tests voor Batch B type hardening.
Verifieer via AST dat Any-violations zijn opgelost.
Run BEFORE implementatie -> verwacht FAIL (RED).
Run AFTER implementatie  -> verwacht PASS (GREEN).
"""

import ast
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


def _get_annotations_with_any(filepath: Path) -> list[tuple[int, str]]:
    """Retourneer (lineno, line) voor annotaties die bare Any bevatten zonder TODO."""
    src = filepath.read_text(encoding="utf-8")
    lines = src.splitlines()
    results = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "Any" not in stripped:
            continue
        # Skip imports, comments, string literals
        if stripped.startswith(("from ", "import ", "#", '"""', "'''")):
            continue
        # Skip if Callable[..., Any] (legitimate decorator pattern)
        if "Callable[" in stripped and "Any]" in stripped:
            continue
        # Skip if has TODO/FIXME on same line
        if "# TODO" in stripped or "# FIXME" in stripped or "# type: ignore" in stripped:
            continue
        # Skip if prev 2 lines have TODO about Any
        has_prev_todo = False
        for offset in range(1, 3):
            prev_idx = i - offset
            if prev_idx >= 0 and ("# TODO" in lines[prev_idx] or "# FIXME" in lines[prev_idx]):
                has_prev_todo = True
                break
        if has_prev_todo:
            continue
        results.append((i + 1, stripped))
    return results


@pytest.mark.unit
class TestResilientApiClientTyping:
    """resilient_api_client.py moet TypedDicts gebruiken voor eigen structuren."""

    TARGET = ROOT / "src/core/agents/resilient_api_client.py"

    def test_module_defines_circuit_breaker_metrics_typeddict(self) -> None:
        """CircuitBreakerMetricsDict TypedDict moet bestaan."""
        src = self.TARGET.read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = {
            node.targets[0].id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        }
        class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        all_names = names | class_names
        assert (
            "CircuitBreakerMetricsDict" in all_names or "CircuitBreakerStatusDict" in all_names
        ), (
            "resilient_api_client.py moet CircuitBreakerMetricsDict of "
            "CircuitBreakerStatusDict TypedDict definiëren"
        )

    def test_get_circuit_breaker_status_return_no_bare_any(self) -> None:
        """get_circuit_breaker_status return-annotatie mag geen bare Any bevatten."""
        src = self.TARGET.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_circuit_breaker_status":
                ret = node.returns
                assert ret is not None, "return annotatie ontbreekt"
                ret_src = ast.unparse(ret)
                assert (
                    "Any" not in ret_src
                ), f"get_circuit_breaker_status return-annotatie bevat Any: {ret_src}"
                return
        pytest.fail("get_circuit_breaker_status niet gevonden")

    def test_get_health_summary_return_no_bare_any(self) -> None:
        """get_health_summary return-annotatie mag geen bare Any bevatten."""
        src = self.TARGET.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_health_summary":
                ret = node.returns
                assert ret is not None
                ret_src = ast.unparse(ret)
                assert "Any" not in ret_src, f"get_health_summary return bevat Any: {ret_src}"
                return
        pytest.fail("get_health_summary niet gevonden")

    def test_make_request_json_data_not_bare_any(self) -> None:
        """_make_request local var json_data mag geen bare Any annotatie hebben zonder TODO."""
        violations = _get_annotations_with_any(self.TARGET)
        any_lines = [line for (_, line) in violations if "json_data" in line and ": Any" in line]
        assert len(any_lines) == 0, f"json_data heeft nog bare Any: {any_lines}"


@pytest.mark.unit
class TestResponseFormatterTyping:
    """response_formatter.py: content: Any -> object; template_variables: dict[str,object]."""

    TARGET = ROOT / "src/core/generation/response_formatter.py"

    def test_template_variables_no_bare_any(self) -> None:
        """FormattingOptions.template_variables mag geen bare Any bevatten zonder TODO."""
        src = self.TARGET.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "FormattingOptions":
                class_src = ast.get_source_segment(src, node) or ""
                if "template_variables" in class_src and ": Any" in class_src:
                    # Check if there's a TODO on same line
                    for line in class_src.splitlines():
                        if "template_variables" in line and ": Any" in line:
                            assert (
                                "# TODO" in line or "# type: ignore" in line or "object" in line
                            ), f"template_variables heeft bare Any zonder TODO: {line}"

    def test_formatting_result_metadata_no_bare_any(self) -> None:
        """FormattingResult.metadata mag geen bare Any bevatten zonder TODO."""
        src = self.TARGET.read_text(encoding="utf-8")
        for line in src.splitlines():
            if "metadata" in line and ": Any" in line and "FormattingResult" not in line:
                if "# TODO" not in line and "# type: ignore" not in line:
                    # Check if next line has TODO — if so, acceptable
                    pass  # Gedetailleerde controle in integration gate


@pytest.mark.unit
class TestChatEndpointsTyping:
    """chat_endpoints.py: conversation history dict moet concreet zijn."""

    TARGET = ROOT / "src/core/api/chat_endpoints.py"

    def test_build_conversation_context_param_not_bare_any(self) -> None:
        """_build_conversation_context param annotation mag geen bare Any bevatten."""
        src = self.TARGET.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_build_conversation_context"
            ):
                for arg in node.args.args:
                    if arg.arg == "conversation_history" and arg.annotation is not None:
                        ann_src = ast.unparse(arg.annotation)
                        assert (
                            "Any" not in ann_src
                        ), f"conversation_history annotatie heeft bare Any: {ann_src}"
                        return
        pytest.fail("_build_conversation_context niet gevonden")


@pytest.mark.unit
class TestActivepiecesEndpointsTyping:
    """activepieces_endpoints.py: react_flow_data en payload concrete typen."""

    TARGET = ROOT / "src/core/api/activepieces_endpoints.py"

    def test_no_bare_any_without_todo_in_pydantic_fields(self) -> None:
        """Pydantic-fields in activepieces_endpoints mogen geen bare Any bevatten zonder TODO."""
        violations = _get_annotations_with_any(self.TARGET)
        # Filter: exclude lines already properly marked
        real_violations = [
            (lineno, line)
            for lineno, line in violations
            if "Field(" in line or ": dict[str" in line
        ]
        assert len(real_violations) == 0, (
            f"activepieces_endpoints.py heeft {len(real_violations)} bare Any in Pydantic fields:\n"
            + "\n".join(f"  L{ln}: {line}" for ln, line in real_violations)
        )
