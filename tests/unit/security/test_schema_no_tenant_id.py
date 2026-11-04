"""
Sprint B: Pydantic request schemas must NOT expose tenant_id as a client-settable field.

Rule (CLAUDE.md): tenant_id must always come from the JWT claim via middleware/Depends.
Accepting tenant_id in request bodies lets clients scope to arbitrary tenants.

Strategy: source-scan tests that start RED until each schema is fixed.
These also serve as regression guards — if a future PR re-adds the field, tests fail.

Each test extracts the specific class body and asserts tenant_id is absent.
"""

import re
from pathlib import Path

_SRC = Path(__file__).parents[3] / "src"


def _read(rel: str) -> str:
    return (_SRC / rel).read_text(encoding="utf-8")


def _class_body(source: str, class_name: str) -> str:
    """Extract the lines belonging to a class (until the next top-level def/class)."""
    lines = source.splitlines()
    in_class = False
    body: list[str] = []
    class_indent = 0

    for line in lines:
        m = re.match(r"^(\s*)class\s+" + re.escape(class_name) + r"\b", line)
        if m:
            in_class = True
            class_indent = len(m.group(1))
            body = [line]
            continue

        if in_class:
            stripped = line.lstrip()
            cur_indent = len(line) - len(stripped)
            # End of class: non-empty line at same or lower indent that isn't a decorator/comment
            if stripped and cur_indent <= class_indent and not stripped.startswith("#"):
                break
            body.append(line)

    return "\n".join(body)


def _has_tenant_id_field(class_src: str) -> bool:
    """Return True if the class body contains a tenant_id field definition."""
    return bool(re.search(r"^\s+tenant_id\s*:", class_src, re.MULTILINE))


# ===========================================================================
# GROUP 1 — Direct HTTP endpoint request schemas (highest risk)
# ===========================================================================


class TestAgentQueryRequest:
    """
    AgentQueryRequest.tenant_id lets the caller override which tenant an agent
    query runs for. The endpoint already authenticates via get_current_user_dependency;
    tenant_id must come from current_user.tenant_id, not from the request body.
    """

    _F = "core/api/agent_endpoints.py"
    _C = "AgentQueryRequest"

    def test_no_tenant_id_field(self) -> None:
        body = _class_body(_read(self._F), self._C)
        assert body, f"{self._C} class not found in {self._F}"
        assert not _has_tenant_id_field(body), (
            f"{self._C} must not expose tenant_id — get it from current_user.tenant_id"
        )


class TestToolCreate:
    """
    ToolCreate.tenant_id allows a caller to register a tool under any tenant_id.
    Must be removed; the endpoint injects it from JWT.
    """

    _F = "core/api/v1/tool_broker_shared.py"
    _C = "ToolCreate"

    def test_no_tenant_id_field(self) -> None:
        body = _class_body(_read(self._F), self._C)
        assert body, f"{self._C} class not found in {self._F}"
        assert not _has_tenant_id_field(body), (
            f"{self._C} must not expose tenant_id — inject from JWT Depends"
        )


class TestFocusBuilderFlowCreate:
    """
    core/focus_builder/schemas.py FlowCreate.tenant_id is passed straight to the
    DB insert — anyone can create flows in any tenant's namespace.
    """

    _F = "core/focus_builder/schemas.py"
    _C = "FlowCreate"

    def test_no_tenant_id_field(self) -> None:
        body = _class_body(_read(self._F), self._C)
        assert body, f"{self._C} class not found in {self._F}"
        assert not _has_tenant_id_field(body), (
            f"{self._C} must not expose tenant_id — service must receive it from JWT context"
        )


# Weesen tot 2026-08-27 naar `core/workflow/api.py`, bevestigd dode code (ADR-036 OP-158
# D2b) en verwijderd. `WorkflowCreateRequest`/`WorkflowExecuteRequest` bestaan ONDER
# DEZELFDE NAAM ook in de echte, gemounte routers -- vier plekken, niet een, want elke
# workflow-router definieert zijn eigen kopie. Alle vier hier gedekt in plaats van er een
# te kiezen als "de" kanonieke.


class TestWorkflowCrudRouterCreateRequest:
    """WorkflowCreateRequest in workflow_crud_router.py (de echte create-endpoint)."""

    _F = "core/api/v1/workflow/workflow_crud_router.py"
    _C = "WorkflowCreateRequest"

    def test_no_tenant_id_field(self) -> None:
        body = _class_body(_read(self._F), self._C)
        assert body, f"{self._C} class not found in {self._F}"
        assert not _has_tenant_id_field(body), (
            f"{self._C} must not expose tenant_id — use get_current_tenant Depends"
        )


class TestWorkflowExecutionRouterExecuteRequest:
    """WorkflowExecuteRequest in workflow_execution_router.py."""

    _F = "core/api/v1/workflow/workflow_execution_router.py"
    _C = "WorkflowExecuteRequest"

    def test_no_tenant_id_field(self) -> None:
        body = _class_body(_read(self._F), self._C)
        assert body, f"{self._C} class not found in {self._F}"
        assert not _has_tenant_id_field(body), (
            f"{self._C} must not expose tenant_id — use get_current_tenant Depends"
        )


class TestWorkflowExecutionCoreRouterExecuteRequest:
    """WorkflowExecuteRequest in workflow_execution_core_router.py."""

    _F = "core/api/v1/workflow/workflow_execution_core_router.py"
    _C = "WorkflowExecuteRequest"

    def test_no_tenant_id_field(self) -> None:
        body = _class_body(_read(self._F), self._C)
        assert body, f"{self._C} class not found in {self._F}"
        assert not _has_tenant_id_field(body), (
            f"{self._C} must not expose tenant_id — use get_current_tenant Depends"
        )


class TestWorkflowExecutionApRouterExecuteRequest:
    """WorkflowExecuteRequest in workflow_execution_ap_router.py (ActivePieces-pad)."""

    _F = "core/api/v1/workflow/workflow_execution_ap_router.py"
    _C = "WorkflowExecuteRequest"

    def test_no_tenant_id_field(self) -> None:
        body = _class_body(_read(self._F), self._C)
        assert body, f"{self._C} class not found in {self._F}"
        assert not _has_tenant_id_field(body), (
            f"{self._C} must not expose tenant_id — use get_current_tenant Depends"
        )


class TestRouteDebugRequest:
    """
    RouteDebugRequest.tenant_id lets callers debug-route queries as any tenant.
    Debug endpoints still require tenant isolation.
    """

    _F = "core/api/v1/agentic/router_debug.py"
    _C = "RouteDebugRequest"

    def test_no_tenant_id_field(self) -> None:
        body = _class_body(_read(self._F), self._C)
        assert body, f"{self._C} class not found in {self._F}"
        assert not _has_tenant_id_field(body), (
            f"{self._C} must not expose tenant_id — inject from JWT"
        )


class TestTaskExecuteRequest:
    """
    TaskExecuteRequest.tenant_id lets callers execute supervisor tasks in any tenant.
    """

    _F = "core/api/v1/agentic/supervisors.py"
    _C = "TaskExecuteRequest"

    def test_no_tenant_id_field(self) -> None:
        body = _class_body(_read(self._F), self._C)
        assert body, f"{self._C} class not found in {self._F}"
        assert not _has_tenant_id_field(body), (
            f"{self._C} must not expose tenant_id — inject from JWT"
        )


class TestSuggestionRequest:
    """
    SuggestionRequest.tenant_id defaults to 1 — any unauthenticated caller gets
    tenant-1 suggestions. Must be removed and injected from JWT.
    """

    _F = "core/services/focus_suggestion_service.py"
    _C = "SuggestionRequest"

    def test_no_tenant_id_field(self) -> None:
        body = _class_body(_read(self._F), self._C)
        assert body, f"{self._C} class not found in {self._F}"
        assert not _has_tenant_id_field(body), (
            f"{self._C} must not expose tenant_id (was defaulting to 1)"
        )


# ===========================================================================
# GROUP 2 — ALS internal schemas (agent-facing API — still client-controlled)
# ===========================================================================


class TestALSCreateSchemas:
    """
    ALS schemas (SignalCreate, AgentRegister, HeartbeatRequest, InsightCreate,
    KnowledgeQuery, CollaborationCreate, SwarmCreate, AntibodyCreate) expose
    tenant_id as a required field. ALS endpoints are protected by JWT auth;
    tenant_id must come from the token, not the payload.
    """

    _F = "core/als/models/schemas.py"

    def _check(self, class_name: str) -> None:
        body = _class_body(_read(self._F), class_name)
        assert body, f"{class_name} class not found in {self._F}"
        assert not _has_tenant_id_field(body), (
            f"{class_name} must not expose tenant_id in ALS API payload — inject from JWT"
        )

    def test_signal_create_no_tenant_id(self) -> None:
        self._check("SignalCreate")

    def test_agent_register_no_tenant_id(self) -> None:
        self._check("AgentRegister")

    def test_heartbeat_request_no_tenant_id(self) -> None:
        self._check("HeartbeatRequest")

    def test_insight_create_no_tenant_id(self) -> None:
        self._check("InsightCreate")

    def test_knowledge_query_no_tenant_id(self) -> None:
        self._check("KnowledgeQuery")

    def test_collaboration_create_no_tenant_id(self) -> None:
        self._check("CollaborationCreate")

    def test_swarm_create_no_tenant_id(self) -> None:
        self._check("SwarmCreate")

    def test_antibody_create_no_tenant_id(self) -> None:
        self._check("AntibodyCreate")
