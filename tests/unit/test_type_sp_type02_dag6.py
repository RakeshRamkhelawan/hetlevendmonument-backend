"""
SP-TYPE-02 Group B -- AST regression tests for Governance + Knowledge + Events + Domains.

One test class per changed file. Each test parses the source with the stdlib
`ast` module and asserts that:
  - Dead legacy typing imports (Dict, List, Optional, Union) are gone.
  - New concrete annotations are present where HIGH-confidence narrowing was applied.

No imports from the production modules are required, so these tests run under
--collect-only without triggering any side effects.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # repo root


def _imported_names(rel: str) -> set[str]:
    """Return every name imported from `typing` in the given source file."""
    path = ROOT / rel
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            for alias in node.names:
                names.add(alias.name)
    return names


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# compliance_guardian.py -- TYPE_CHECKING + empty block removed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComplianceGuardianImports:
    """TYPE_CHECKING import and empty if TYPE_CHECKING block removed."""

    FILE = "src/core/governance/compliance_guardian.py"

    def test_type_checking_not_imported(self) -> None:
        assert "TYPE_CHECKING" not in _imported_names(self.FILE), (
            "TYPE_CHECKING was imported but the `if TYPE_CHECKING:` block was empty -- remove it"
        )

    def test_any_still_imported(self) -> None:
        # Any is legitimately used for external service parameters
        assert "Any" in _imported_names(self.FILE)

    def test_no_empty_if_type_checking_block(self) -> None:
        src = _source(self.FILE)
        assert "if TYPE_CHECKING:" not in src, (
            "Empty `if TYPE_CHECKING:` block should be removed along with the import"
        )


# ---------------------------------------------------------------------------
# rate_limiter.py -- Optional removed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRateLimiterImports:
    """Optional removed from rate_limiter.py -- was imported but never used."""

    FILE = "src/core/governance/rate_limiter.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in rate_limiter.py -- use X | None syntax instead"
        )

    def test_any_still_imported(self) -> None:
        # Any is legitimately used in Callable[..., Any] decorator signatures
        assert "Any" in _imported_names(self.FILE)


# ---------------------------------------------------------------------------
# cookie_consent.py -- Optional removed; ts narrowed to datetime | None
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCookieConsentTypes:
    """Optional removed; getattr result narrowed from Any to datetime | None."""

    FILE = "src/core/governance/cookie_consent.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in cookie_consent.py -- use X | None syntax instead"
        )

    def test_ts_narrowed_to_datetime_or_none(self) -> None:
        src = _source(self.FILE)
        assert "ts: datetime | None" in src, (
            "_db_to_preferences local var `ts` must be annotated as `datetime | None`, not `Any`"
        )
        assert "ts: Any" not in src, (
            "`ts` must not be typed as `Any` -- it is always a datetime or None"
        )


# ---------------------------------------------------------------------------
# sharding.py -- _analyze_event and _handle_violations narrowed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestShardingTypes:
    """_analyze_event return type and _handle_violations param narrowed from Any."""

    FILE = "src/core/governance/governance_agent/sharding.py"

    def test_analyze_event_returns_dict_or_none(self) -> None:
        tree = ast.parse((ROOT / self.FILE).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_analyze_event":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert "dict[str, Any]" in ret, (
                    f"_analyze_event should return 'dict[str, Any] | None', got {ret!r}"
                )
                assert "None" in ret, f"_analyze_event return must include None, got {ret!r}"
                return
        pytest.fail("_analyze_event not found in sharding.py")

    def test_handle_violations_param_is_list_of_dict(self) -> None:
        tree = ast.parse((ROOT / self.FILE).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_handle_violations":
                for arg in node.args.args:
                    if arg.arg == "violations":
                        annotation = ast.unparse(arg.annotation) if arg.annotation else ""
                        assert "dict[str, Any]" in annotation, (
                            f"violations param should use list[dict[str, Any]], got {annotation!r}"
                        )
                        return
        pytest.fail("_handle_violations not found in sharding.py")


# ---------------------------------------------------------------------------
# knowledge_service.py -- Optional removed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestKnowledgeServiceImports:
    """Optional removed from knowledge_service.py -- was imported but never used."""

    FILE = "src/core/knowledge/knowledge_service.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in knowledge_service.py -- use X | None syntax instead"
        )

    def test_any_still_imported(self) -> None:
        # Any is legitimately used in dict[str, Any] for metadata fields
        assert "Any" in _imported_names(self.FILE)


# ---------------------------------------------------------------------------
# sop_executor.py -- Dict, List, Optional removed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSOPExecutorImports:
    """Dict, List, Optional removed from sop_executor.py -- were imported but never used."""

    FILE = "src/core/knowledge/sops/sop_executor.py"

    def test_dict_not_imported(self) -> None:
        assert "Dict" not in _imported_names(self.FILE), (
            "Dict is a legacy typing alias -- use built-in dict[] instead"
        )

    def test_list_not_imported(self) -> None:
        assert "List" not in _imported_names(self.FILE), (
            "List is a legacy typing alias -- use built-in list[] instead"
        )

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in sop_executor.py -- use X | None syntax instead"
        )

    def test_any_still_imported(self) -> None:
        # Any is legitimately used for tool_broker and recursive param resolution
        assert "Any" in _imported_names(self.FILE)


# ---------------------------------------------------------------------------
# pubsub_manager.py -- Dict, List, Optional removed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPubSubManagerImports:
    """Dict, List, Optional removed from pubsub_manager.py -- were imported but never used."""

    FILE = "src/core/events/pubsub_manager.py"

    def test_dict_not_imported(self) -> None:
        assert "Dict" not in _imported_names(self.FILE), (
            "Dict is a legacy typing alias -- use built-in dict[] instead"
        )

    def test_list_not_imported(self) -> None:
        assert "List" not in _imported_names(self.FILE), (
            "List is a legacy typing alias -- use built-in list[] instead"
        )

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in pubsub_manager.py -- use X | None syntax instead"
        )

    def test_any_still_imported(self) -> None:
        # Any is legitimately used for pubsub client and message data dicts
        assert "Any" in _imported_names(self.FILE)


# ---------------------------------------------------------------------------
# observability.py -- List, Optional removed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestObservabilityImports:
    """List, Optional removed from observability.py -- were imported but never used."""

    FILE = "src/domains/memory/observability.py"

    def test_list_not_imported(self) -> None:
        assert "List" not in _imported_names(self.FILE), (
            "List is a legacy typing alias -- use built-in list[] instead"
        )

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in observability.py -- use X | None syntax instead"
        )

    def test_any_still_imported(self) -> None:
        # Any is legitimately used for prometheus metric factory return types
        assert "Any" in _imported_names(self.FILE)


# ---------------------------------------------------------------------------
# experiments.py -- Any import removed; endpoints return concrete types
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExperimentsEndpointTypes:
    """Any import removed; all four endpoint return types are now concrete."""

    FILE = "src/domains/agentic/api/experiments.py"

    def test_any_not_imported(self) -> None:
        assert "Any" not in _imported_names(self.FILE), (
            "Any is no longer needed in experiments.py after narrowing all endpoint return types"
        )

    def test_create_experiment_returns_experiment_response(self) -> None:
        tree = ast.parse((ROOT / self.FILE).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_experiment":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert ret == "ExperimentResponse", (
                    f"create_experiment should return ExperimentResponse, got {ret!r}"
                )
                return
        pytest.fail("create_experiment not found in experiments.py")

    def test_list_experiments_returns_list_of_experiment_response(self) -> None:
        tree = ast.parse((ROOT / self.FILE).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "list_experiments":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert "ExperimentResponse" in ret, (
                    f"list_experiments should return list[ExperimentResponse], got {ret!r}"
                )
                return
        pytest.fail("list_experiments not found in experiments.py")

    def test_promote_experiment_returns_dict_str_str(self) -> None:
        tree = ast.parse((ROOT / self.FILE).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "promote_experiment":
                ret = ast.unparse(node.returns) if node.returns else ""
                assert ret == "dict[str, str]", (
                    f"promote_experiment should return dict[str, str], got {ret!r}"
                )
                return
        pytest.fail("promote_experiment not found in experiments.py")


# ---------------------------------------------------------------------------
# chat_service.py -- Dict, List, Optional removed; serialized_tool_calls narrowed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestChatServiceTypes:
    """Dict, List, Optional removed; serialized_tool_calls narrowed from Any."""

    FILE = "src/domains/agentic/services/chat_service.py"

    def test_dict_not_imported(self) -> None:
        assert "Dict" not in _imported_names(self.FILE), (
            "Dict is a legacy typing alias -- use built-in dict[] instead"
        )

    def test_list_not_imported(self) -> None:
        assert "List" not in _imported_names(self.FILE), (
            "List is a legacy typing alias -- use built-in list[] instead"
        )

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in chat_service.py -- use X | None syntax instead"
        )

    def test_serialized_tool_calls_narrowed(self) -> None:
        src = _source(self.FILE)
        assert "serialized_tool_calls: list[dict[str, Any]] | None" in src, (
            "serialized_tool_calls must be typed as list[dict[str, Any]] | None, not Any"
        )
        assert "serialized_tool_calls: Any" not in src, (
            "serialized_tool_calls must not be typed as Any"
        )


# ---------------------------------------------------------------------------
# experimentation_service.py -- Optional removed
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExperimentationServiceImports:
    """Optional removed from experimentation_service.py -- was imported but never used."""

    FILE = "src/domains/agentic/services/experimentation_service.py"

    def test_optional_not_imported(self) -> None:
        assert "Optional" not in _imported_names(self.FILE), (
            "Optional is unused in experimentation_service.py -- use X | None syntax instead"
        )

    def test_any_still_imported(self) -> None:
        # Any is legitimately used for ab_framework call results (awaitable-or-not pattern)
        assert "Any" in _imported_names(self.FILE)
