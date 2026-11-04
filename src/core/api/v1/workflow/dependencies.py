# orphan:exempt reason: Laag 1 dependencies, re-exports shared deps for v1/workflow/ sub-routers (ADR-033)
"""
Re-exports shared dependencies for workflow sub-routers (ADR-033 Laag 1).
"""

from collections.abc import Callable
from typing import Any

from src.core.api.dependencies import get_db  # noqa: F401
from src.core.auth.api_deps import require_scopes, OAuth2Scope  # noqa: F401
from src.core.middleware.tenant_context import get_current_tenant_id  # noqa: F401

# Workflow domain models en services (ADR-033: verboden in router-bestanden)
from src.core.agents.execution_feedback_agent import ExecutionFeedbackAgent  # noqa: F401
from src.core.agents.workflow_orchestrator_agent import WorkflowOrchestratorAgent  # noqa: F401
from src.core.llm.llm_service import LLMService  # noqa: F401
from src.core.workflow.cancellation import CancellationScope, GracefulCanceller  # noqa: F401
from src.core.workflow.engine import ProductionWorkflowEngine  # noqa: F401
from src.core.workflow.interfaces import (  # noqa: F401
    IAgentRuntime,
    ILLMProvider,
    IToolBroker,
    TaskExecutionRequest,
    TaskExecutionResult,
)
from src.core.workflow.models import (  # noqa: F401
    C7ExecutionTask,
    C7Workflow,
    C7WorkflowExecution,
    WorkflowStatus,
)
from src.core.workflow.schemas import (  # noqa: F401
    RefinementSuggestion,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
)
from src.core.services.workflow_generator_service import create_workflow_generator  # noqa: F401
from src.core.services.workflow_service import WorkflowService  # noqa: F401
from src.core.services.workflow_versioning_service import WorkflowVersioningService  # noqa: F401
from src.core.workflow.stap_overzicht import stap_overzicht  # noqa: F401
from src.core.shared.rate_limiter import privacy_rate_limit
from src.core.workflow.visualizer import visualizer  # noqa: F401



def consent_read_limit(func: Callable[..., Any]) -> Callable[..., Any]:
    """60 verzoeken per minuut per medewerker, hetzelfde als `governance.rate_limiter.consent_read_limit`.

    Bewust hier uit `shared` opgebouwd en niet uit `governance` gehaald: de router mag governance niet rechtstreeks kennen
    (ADR-033) en een extra importpaar naar governance liet het fan-out-budget van `core_api` overschrijden (569). Het getal
    wordt bewaakt door `tests/unit/api/test_uitvoerbare_agents_heeft_een_limiet.py` (de 61e aanroep geeft 429).
    """
    return privacy_rate_limit(max_requests=60, window_seconds=60)(func)


__all__ = [
    "get_db",
    "require_scopes",
    "OAuth2Scope",
    "get_current_tenant_id",
    # Workflow domain
    "ExecutionFeedbackAgent",
    "WorkflowOrchestratorAgent",
    "LLMService",
    "CancellationScope",
    "GracefulCanceller",
    "ProductionWorkflowEngine",
    "IAgentRuntime",
    "ILLMProvider",
    "IToolBroker",
    "TaskExecutionRequest",
    "TaskExecutionResult",
    "C7ExecutionTask",
    "C7Workflow",
    "C7WorkflowExecution",
    "WorkflowStatus",
    "visualizer",
    "stap_overzicht",
    "consent_read_limit",
    # Services (ADR-033: facade for router-level access)
    "create_workflow_generator",
    "WorkflowService",
    "WorkflowVersioningService",
    # Workflow schemas (ADR-033: facade for router-level access)
    "WorkflowDefinition",
    "WorkflowNode",
    "WorkflowEdge",
    "RefinementSuggestion",
]
