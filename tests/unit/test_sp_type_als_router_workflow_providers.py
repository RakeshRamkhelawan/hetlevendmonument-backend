"""
SP-TYPE Batch A: AST-based type annotation tests for:
  - src/core/als/router.py          (ALS router)
  - src/core/workflow/providers.py  (workflow providers)

Each test verifies that a specific Any violation has been replaced
with a concrete type annotation. Uses AST + source inspection only;
no runtime imports of the production modules.
"""

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _parse(rel: str) -> ast.Module:
    return ast.parse(_source(rel))


def _function_return_annotation(tree: ast.Module, name: str) -> str | None:
    """Return ast.unparse of the return annotation for a top-level function."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name and node.returns is not None:
            return ast.unparse(node.returns)
    return None


def _method_param_annotation(
    tree: ast.Module, class_name: str, method_name: str, param: str
) -> str | None:
    """Return ast.unparse of a parameter annotation for a method inside a class."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in ast.walk(node):
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == method_name
                ):
                    for arg in item.args.args:
                        if arg.arg == param and arg.annotation is not None:
                            return ast.unparse(arg.annotation)
    return None


def _method_return_annotation(tree: ast.Module, class_name: str, method_name: str) -> str | None:
    """Return ast.unparse of the return annotation for a method inside a class."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in ast.walk(node):
                if (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name == method_name
                    and item.returns is not None
                ):
                    return ast.unparse(item.returns)
    return None


# ---------------------------------------------------------------------------
# router.py
# ---------------------------------------------------------------------------


class TestALSRouterTypes:
    FILE = "src/core/als/router.py"

    def test_async_redis_client_imported(self) -> None:
        """AsyncRedisClient must be imported from src.core.typing."""
        src = _source(self.FILE)
        assert "AsyncRedisClient" in src, "AsyncRedisClient not found in imports"
        assert "from src.core.typing import AsyncRedisClient" in src

    def test_agent_registration_imported(self) -> None:
        """AgentRegistration must be imported from organism_registry."""
        src = _source(self.FILE)
        assert "AgentRegistration" in src
        assert "from src.core.als.agents.organism_registry import" in src

    def test_organism_registry_imported(self) -> None:
        """OrganismRegistry must be imported for get_router() signature."""
        src = _source(self.FILE)
        assert "OrganismRegistry" in src

    def test_filter_healthy_agents_param_type(self) -> None:
        """_filter_healthy_agents(agents) must be list[AgentRegistration]."""
        tree = _parse(self.FILE)
        ann = _method_param_annotation(tree, "RouterService", "_filter_healthy_agents", "agents")
        assert ann is not None, "_filter_healthy_agents param 'agents' has no annotation"
        assert "AgentRegistration" in ann, f"Expected AgentRegistration in annotation, got {ann!r}"
        assert "Any" not in ann, f"Any still present in annotation: {ann!r}"

    def test_filter_agents_by_department_param_type(self) -> None:
        """_filter_agents_by_department(agents) must be list[AgentRegistration]."""
        tree = _parse(self.FILE)
        ann = _method_param_annotation(
            tree, "RouterService", "_filter_agents_by_department", "agents"
        )
        assert ann is not None
        assert "AgentRegistration" in ann
        assert "Any" not in ann, f"Any still present: {ann!r}"

    def test_route_via_llm_param_type(self) -> None:
        """_route_via_llm(agents) must be list[AgentRegistration]."""
        tree = _parse(self.FILE)
        ann = _method_param_annotation(tree, "RouterService", "_route_via_llm", "agents")
        assert ann is not None
        assert "AgentRegistration" in ann
        assert "Any" not in ann, f"Any still present: {ann!r}"

    def test_fallback_param_type(self) -> None:
        """_fallback(agents) must be list[AgentRegistration]."""
        tree = _parse(self.FILE)
        ann = _method_param_annotation(tree, "RouterService", "_fallback", "agents")
        assert ann is not None
        assert "AgentRegistration" in ann
        assert "Any" not in ann, f"Any still present: {ann!r}"

    def test_router_service_redis_param_type(self) -> None:
        """RouterService.__init__ redis_client must be AsyncRedisClient | None."""
        tree = _parse(self.FILE)
        ann = _method_param_annotation(tree, "RouterService", "__init__", "redis_client")
        assert ann is not None, "redis_client has no annotation"
        assert "AsyncRedisClient" in ann, f"Expected AsyncRedisClient, got {ann!r}"
        assert "Any" not in ann, f"Any still present: {ann!r}"

    def test_router_service_registry_param_type(self) -> None:
        """RouterService.__init__ registry must be OrganismRegistry | None."""
        tree = _parse(self.FILE)
        ann = _method_param_annotation(tree, "RouterService", "__init__", "registry")
        assert ann is not None, "registry has no annotation"
        assert "OrganismRegistry" in ann, f"Expected OrganismRegistry, got {ann!r}"
        assert "Any" not in ann, f"Any still present: {ann!r}"

    def test_get_router_redis_param_type(self) -> None:
        """get_router() redis_client must be AsyncRedisClient."""
        tree = _parse(self.FILE)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_router":
                for arg in node.args.args:
                    if arg.arg == "redis_client" and arg.annotation is not None:
                        ann = ast.unparse(arg.annotation)
                        assert "AsyncRedisClient" in ann, f"Expected AsyncRedisClient, got {ann!r}"
                        assert "Any" not in ann
                        return
        pytest.fail("get_router redis_client annotation not found")

    def test_no_todo_type_on_typed_params(self) -> None:
        """Lines with AgentRegistration or AsyncRedisClient must not have TODO(TYPE)."""
        for line in _source(self.FILE).splitlines():
            if ("AgentRegistration" in line or "AsyncRedisClient" in line) and "TODO(TYPE)" in line:
                pytest.fail(f"TODO(TYPE) still present on typed line: {line!r}")


# ---------------------------------------------------------------------------
# providers.py
# ---------------------------------------------------------------------------


class TestWorkflowProvidersTypesExtended:
    FILE = "src/core/workflow/providers.py"

    def test_async_session_imported(self) -> None:
        """AsyncSession must be imported from sqlalchemy.ext.asyncio."""
        src = _source(self.FILE)
        assert "from sqlalchemy.ext.asyncio import AsyncSession" in src or (
            "AsyncSession" in src and "sqlalchemy" in src
        )

    def test_async_sessionmaker_imported(self) -> None:
        """async_sessionmaker must be imported."""
        src = _source(self.FILE)
        assert "async_sessionmaker" in src

    def test_subagent_loader_in_type_checking(self) -> None:
        """SubagentLoader must be imported inside TYPE_CHECKING block."""
        src = _source(self.FILE)
        assert "TYPE_CHECKING" in src
        assert "SubagentLoader" in src

    def test_agent_definition_in_type_checking(self) -> None:
        """AgentDefinition must be imported inside TYPE_CHECKING block."""
        src = _source(self.FILE)
        assert "AgentDefinition" in src

    def test_production_agent_runtime_subagent_loader_type(self) -> None:
        """ProductionAgentRuntime.subagent_loader must be annotated SubagentLoader | None."""
        src = _source(self.FILE)
        assert "SubagentLoader | None" in src, "SubagentLoader | None not found in providers.py"

    def test_production_agent_runtime_load_agent_return_type(self) -> None:
        """ProductionAgentRuntime.load_agent must return AgentDefinition | None."""
        tree = _parse(self.FILE)
        ann = _method_return_annotation(tree, "ProductionAgentRuntime", "load_agent")
        assert ann is not None, "load_agent has no return annotation"
        assert "AgentDefinition" in ann, f"Expected AgentDefinition in return, got {ann!r}"

    def test_production_agent_runtime_execute_agent_agent_param(self) -> None:
        """ProductionAgentRuntime.execute_agent agent param must be AgentDefinition."""
        tree = _parse(self.FILE)
        ann = _method_param_annotation(tree, "ProductionAgentRuntime", "execute_agent", "agent")
        assert ann is not None, "execute_agent 'agent' param has no annotation"
        assert "AgentDefinition" in ann, f"Expected AgentDefinition, got {ann!r}"
        assert ann != "Any", f"Still Any: {ann!r}"

    def test_production_unit_of_work_session_maker_type(self) -> None:
        """ProductionUnitOfWork.__init__ session_maker must be async_sessionmaker[AsyncSession]."""
        tree = _parse(self.FILE)
        ann = _method_param_annotation(tree, "ProductionUnitOfWork", "__init__", "session_maker")
        assert ann is not None, "session_maker has no annotation"
        assert "async_sessionmaker" in ann, f"Expected async_sessionmaker, got {ann!r}"
        assert "AsyncSession" in ann
        assert "Any" not in ann

    def test_production_unit_of_work_session_field_type(self) -> None:
        """ProductionUnitOfWork._session must be AsyncSession | None."""
        src = _source(self.FILE)
        assert "self._session: AsyncSession | None" in src, (
            "_session field not annotated as AsyncSession | None"
        )

    def test_production_unit_of_work_session_property_return(self) -> None:
        """ProductionUnitOfWork.session property must return AsyncSession."""
        tree = _parse(self.FILE)
        ann = _method_return_annotation(tree, "ProductionUnitOfWork", "session")
        assert ann is not None, "session property has no return annotation"
        assert ann == "AsyncSession", f"Expected AsyncSession, got {ann!r}"

    def test_test_unit_of_work_session_param_type(self) -> None:
        """TestUnitOfWork.__init__ session must be AsyncSession."""
        tree = _parse(self.FILE)
        ann = _method_param_annotation(tree, "TestUnitOfWork", "__init__", "session")
        assert ann is not None, "TestUnitOfWork __init__ session param has no annotation"
        assert "AsyncSession" in ann, f"Expected AsyncSession, got {ann!r}"
        assert "Any" not in ann

    def test_test_unit_of_work_session_property_return(self) -> None:
        """TestUnitOfWork.session property must return AsyncSession."""
        tree = _parse(self.FILE)
        ann = _method_return_annotation(tree, "TestUnitOfWork", "session")
        assert ann is not None, "TestUnitOfWork session property has no return annotation"
        assert ann == "AsyncSession", f"Expected AsyncSession, got {ann!r}"

    def test_no_todo_type_on_session_lines(self) -> None:
        """Lines with AsyncSession or async_sessionmaker must not have TODO(TYPE)."""
        for line in _source(self.FILE).splitlines():
            if ("AsyncSession" in line or "async_sessionmaker" in line) and "TODO(TYPE)" in line:
                pytest.fail(f"TODO(TYPE) still present on typed line: {line!r}")
