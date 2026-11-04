"""
CVA Tool Definitions for Gemini Function Calling
"""

from typing import Any, Literal, cast, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.agents.ultimate_cva.agent import UltimateCVAAgent

from pydantic import BaseModel, Field

# Lazy imports to avoid circular dependencies or runtime errors if modules aren't ready
hybrid_search: Any = None
try:
    from src.core.search.hybrid_search import hybrid_search as _hybrid_search

    hybrid_search = _hybrid_search
except ImportError:
    pass

notification_service: Any = None
NotificationType: Any = None
try:
    from src.core.services.notification_service import NotificationType as _NotificationType
    from src.core.services.notification_service import notification_service as _notification_service

    notification_service = _notification_service
    NotificationType = _NotificationType
except ImportError:
    pass

# Performance Tools Import
get_system_metrics: Any = None
try:
    from .performance import get_system_metrics as _get_system_metrics  # type: ignore[attr-defined]

    get_system_metrics = _get_system_metrics
except ImportError:  # pragma: no cover - optional if file missing
    pass

# ============================================================================
# Tool Parameter Models
# ============================================================================


class WorkflowNode(BaseModel):
    """A node in a workflow"""

    id: str = Field(description="Unique node identifier")
    agent_name: str = Field(
        description="Agent type: slack_agent, email_agent, llm_summarizer, etc."
    )
    label: str = Field(description="Human-readable label")
    config: dict[str, object] = Field(default_factory=dict, description="Node configuration")
    position: dict[str, int] = Field(default_factory=lambda: {"x": 0, "y": 0})


class WorkflowEdge(BaseModel):
    """An edge connecting two nodes"""

    source: str = Field(description="Source node ID")
    target: str = Field(description="Target node ID")
    condition: str | None = Field(default=None, description="Optional condition")


class CreateWorkflowParams(BaseModel):
    """Parameters for workflow creation"""

    name: str = Field(description="Workflow name")
    description: str = Field(description="Workflow description")
    nodes: list[WorkflowNode] = Field(description="List of workflow nodes")
    edges: list[WorkflowEdge] = Field(description="List of connections between nodes")


class NavigateToParams(BaseModel):
    """Parameters for navigation"""

    route: Literal["/dashboard", "/workflows", "/vibe", "/agents", "/settings", "/analytics"]
    query_params: dict[str, str] | None = Field(
        default=None, description="Optional URL parameters"
    )


class GenerateContentParams(BaseModel):
    """Parameters for content generation"""

    content_type: Literal["newsletter", "website_article", "linkedin_post"]
    topic: str = Field(description="Topic or description for content")
    language: str = Field(default="en-GB", description="Language code")
    style_guidelines: str | None = Field(default=None)


class SearchKnowledgeBaseParams(BaseModel):
    """Parameters for knowledge base search"""

    tenant_id: str = Field(..., description="Current tenant ID")
    query: str = Field(..., description="Search query text")
    filters: dict[str, object] | None = Field(default=None, description="Optional metadata filters")
    limit: int = Field(default=5, ge=1, le=50, description="Max number of results")


class SendNotificationParams(BaseModel):
    """Parameters for sending notifications"""

    target_type: Literal["user", "tenant", "broadcast"] = Field(
        ..., description='"user", "tenant" or "broadcast"'
    )
    tenant_id: str | None = Field(
        default=None, description="Tenant ID (required for user/tenant targets)"
    )
    user_id: str | None = Field(
        default=None, description="User ID (required for target_type='user')"
    )
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification body text")

    level: Literal["info", "success", "warning", "error", "system"] = Field(
        default="info",
        description="Notification level",
    )


class DelegateTaskParams(BaseModel):
    """Parameters for delegating tasks to other agents"""

    target_agent: str = Field(..., description="Target agent ID or type")
    task_description: str = Field(..., description="Detailed description of the task")
    priority: Literal["low", "medium", "high", "critical"] = Field(default="medium")
    context_data: dict[str, object] | None = Field(default=None, description="Context data")


class ManageSystemParams(BaseModel):
    """Parameters for system-wide control"""

    action: Literal["shutdown", "restart", "optimize", "maintenance_mode"] = Field(
        ..., description="Action to perform"
    )
    target_service: str | None = Field(default=None, description="Specific service to target")
    reason: str = Field(..., description="Reason for the action")


class GetSystemMetricsParams(BaseModel):
    """Parameters for fetching Prometheus metrics"""

    window: str = Field(
        default="5m", description="Time window for metrics analysis (e.g. 5m, 1h, 24h)"
    )


# ============================================================================
# Tool Definitions for Gemini
# ============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "create_workflow",
        "description": "Create a new automated workflow with nodes and edges.",
        "parameters_schema": CreateWorkflowParams.model_json_schema(),
    },
    {
        "name": "navigate_to",
        "description": """Navigate the user to a different page in the application.

Route mappings:
- /vibe: VIBE Visual Workflow Builder (for creating/editing workflows visually)
- /workflows: Workflows management page (overview of all workflows)
- /agents: Agents management page (view and manage all agents)
- /dashboard: Main dashboard (overview of system status and metrics)
- /settings: Settings page (configuration and preferences)
- /analytics: Analytics page (performance metrics and insights)

Use /vibe when user asks to "open workflow builder", "create workflow visually", or "use VIBE".""",
        "parameters_schema": NavigateToParams.model_json_schema(),
    },
    {
        "name": "generate_content",
        "description": "Generate marketing content like newsletters, articles, or social posts",
        "parameters_schema": GenerateContentParams.model_json_schema(),
    },
    {
        "name": "get_system_status",
        "description": "Get current system health, active agents, and metrics",
        "parameters_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_system_metrics",
        "description": "Get low-level performance metrics (CPU, Latency, Error Rate) from Prometheus.",
        "parameters_schema": GetSystemMetricsParams.model_json_schema(),
    },
    {
        "name": "search_workflows",
        "description": "Search existing workflows by name or description",
        "parameters_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "search_knowledge_base",
        "description": "Search the tenant-specific knowledge base for documents or domain knowledge.",
        "parameters_schema": SearchKnowledgeBaseParams.model_json_schema(),
    },
    {
        "name": "send_notification",
        "description": "Send an in-app/WebSocket notification to a user, tenant, or broadcast.",
        "parameters_schema": SendNotificationParams.model_json_schema(),
    },
    {
        "name": "delegate_task",
        "description": "Delegate a task to another specialized agent (e.g. WorkflowWorker, AIService).",
        "parameters_schema": DelegateTaskParams.model_json_schema(),
    },
    {
        "name": "manage_system",
        "description": "Perform system-wide control actions like optimization or maintenance.",
        "parameters_schema": ManageSystemParams.model_json_schema(),
    },
]

# ============================================================================
# Tool Executor
# ============================================================================


class ToolExecutor:
    """Execute tools called by the LLM"""

    def __init__(self, agent: "UltimateCVAAgent") -> None:
        self.agent = agent

    def _get_tenant_id(self) -> str:
        """
        Securely retrieve tenant_id from the agent's context.
        This prevents prompt injection attacks from overriding the tenant scope.
        """
        # Falls back to "unknown_tenant" if not set, effectively blocking access
        return getattr(self.agent, "current_tenant_id", "unknown_tenant")

    async def execute(self, tool_name: str, params: dict[str, object]) -> dict[str, object]:
        """Execute a tool and return results"""

        # SECURITY: Enforce tenant_id from backend context for sensitive tools
        # We override any tenant_id provided in the params with the authenticated session's tenant_id
        safe_params = params.copy()
        safe_params["tenant_id"] = self._get_tenant_id()

        if tool_name == "create_workflow":
            return await self._create_workflow(CreateWorkflowParams(**cast(dict[str, Any], params)))  # TODO(TYPE): cast to Any
        elif tool_name == "navigate_to":
            return await self._navigate_to(NavigateToParams(**cast(dict[str, Any], params)))  # TODO(TYPE): cast to Any
        elif tool_name == "generate_content":
            return await self._generate_content(GenerateContentParams(**cast(dict[str, Any], params)))  # TODO(TYPE): cast to Any
        elif tool_name == "get_system_status":
            return await self._get_system_status(cast(str | None, params.get("auth_token")))
        elif tool_name == "search_workflows":
            return await self._search_workflows(cast(str, params.get("query", "")))
        elif tool_name == "search_knowledge_base":
            return await self._search_knowledge_base(SearchKnowledgeBaseParams(**cast(dict[str, Any], safe_params)))  # TODO(TYPE): cast to Any
        elif tool_name == "send_notification":
            return await self._send_notification(SendNotificationParams(**cast(dict[str, Any], safe_params)))  # TODO(TYPE): cast to Any
        elif tool_name == "delegate_task":
            return await self._delegate_task(
                DelegateTaskParams(**cast(dict[str, Any], safe_params)), cast(str | None, params.get("auth_token"))  # TODO(TYPE): cast to Any
            )
        elif tool_name == "manage_system":
            return await self._manage_system(
                ManageSystemParams(**cast(dict[str, Any], safe_params)), cast(str | None, params.get("auth_token"))  # TODO(TYPE): cast to Any
            )
        elif tool_name == "get_system_metrics":
            return await self._get_system_metrics(GetSystemMetricsParams(**cast(dict[str, Any], params)))  # TODO(TYPE): cast to Any
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    async def _create_workflow(self, params: CreateWorkflowParams) -> dict[str, object]:
        """Create workflow and signal navigation to Vibe"""
        return {
            "success": True,
            "workflow_id": f"wf_{id(params)}",
            "action": "navigate_to_vibe",
            "workflow_data": params.model_dump(),
            "message": f"Created workflow '{params.name}' with {len(params.nodes)} nodes",
        }

    async def _navigate_to(self, params: NavigateToParams) -> dict[str, object]:
        """Return navigation instruction"""
        return {
            "success": True,
            "action": "navigate",
            "route": params.route,
            "query_params": params.query_params,
        }

    async def _generate_content(self, params: GenerateContentParams) -> dict[str, object]:
        """Generate content using LLM"""
        content = await self.agent.llm_service.generate_response(
            prompt=f"Generate a {params.content_type} about: {params.topic}. Style: {params.style_guidelines or 'professional'}. Language: {params.language}",
            max_tokens=1000,
        )
        return {
            "success": True,
            "content_type": params.content_type,
            "content": content,
        }

    async def _get_system_status(self, token: str | None = None) -> dict[str, object]:
        """Get system metrics"""
        try:
            return cast(dict[str, object], await self.agent.orchestrator.get_dashboard_data(token))
        except Exception as e:
            return {"error": f"Failed to fetch system status: {e}"}

    async def _search_workflows(self, query: str) -> dict[str, object]:
        """Search workflows (placeholder)"""
        return {
            "success": True,
            "results": [],
            "message": f"Found 0 workflows matching '{query}'",
        }

    async def _search_knowledge_base(self, params: SearchKnowledgeBaseParams) -> dict[str, object]:
        """Search tenant-specific knowledge base using hybrid search"""
        if not hybrid_search:
            return {"success": False, "error": "Search service unavailable"}

        try:
            # Convert tenant_id to int for hybrid_search (expects int, not str)
            tenant_id_int = int(params.tenant_id)
            results = await hybrid_search(
                tenant_id=tenant_id_int,
                query=params.query,
                config=None,  # Use default config or map filters if supported
            )

            # Serialize results
            serialized_results: list[dict[str, object]] = []
            for r in results[: params.limit]:
                serialized_results.append(
                    {
                        "content": r.content,
                        "metadata": r.metadata,
                        "score": r.hybrid_score,
                    }
                )

            return {
                "success": True,
                "count": len(serialized_results),
                "results": serialized_results,
                "source": "knowledge_base",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _send_notification(self, params: SendNotificationParams) -> dict[str, object]:
        """Send in-app/WebSocket notification"""
        if not notification_service:
            return {"success": False, "error": "Notification service unavailable"}

        # Check if NotificationType is available (import could fail)
        if NotificationType is None:
            return {"success": False, "error": "Notification type not available"}

        delivered_count = 0
        success = False

        try:
            notif_type = NotificationType(params.level)

            if params.target_type == "user":
                if not params.user_id or not params.tenant_id:
                    return {"success": False, "error": "user_id and tenant_id required"}
                success = await notification_service.notify_user(
                    user_id=params.user_id,
                    title=params.title,
                    message=params.message,
                    type=notif_type,
                )
                delivered_count = 1 if success else 0

            elif params.target_type == "tenant":
                if not params.tenant_id:
                    return {"success": False, "error": "tenant_id required"}
                delivered_count = await notification_service.notify_tenant(
                    tenant_id=params.tenant_id,
                    title=params.title,
                    message=params.message,
                    type=notif_type,
                )
                success = delivered_count > 0

            elif params.target_type == "broadcast":
                delivered_count = await notification_service.broadcast_system(
                    title=params.title,
                    message=params.message,
                )
                success = delivered_count > 0

            return {
                "success": success,
                "delivered_count": delivered_count,
                "target_type": params.target_type,
                "target_id": params.user_id or params.tenant_id,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _delegate_task(
        self, params: DelegateTaskParams, token: str | None = None
    ) -> dict[str, object]:
        """Delegate task via orchestrator"""
        try:
            # Construct payload matching what OrchestratorClient expects or simply forward relevant parts
            # But OrchestratorClient.execute_task_management expects ParsedCommand, etc.
            # We should probably expose a cleaner method on OrchestratorClient or call the raw endpoint.
            # OrchestratorClient._post_multi_agent is the best bet if we build the payload manually.

            payload = {
                "task_type": "delegated_task",
                "target_agent": params.target_agent,
                "description": params.task_description,
                "priority": params.priority,
                "context": params.context_data or {},
                "source": "ultimate_cva",
            }

            return cast(
                dict[str, object], await self.agent.orchestrator._post_multi_agent(payload, token)
            )
        except Exception as e:
            return {"success": False, "error": f"Delegation failed: {e}"}

    async def _manage_system(
        self, params: ManageSystemParams, token: str | None = None
    ) -> dict[str, object]:
        """Execute system control via orchestrator"""
        try:
            payload = {
                "action": params.action,
                "target": params.target_service,
                "reason": params.reason,
                "source": "ultimate_cva",
            }
            return cast(
                dict[str, object],
                await self.agent.orchestrator._post_system_control(payload, token),
            )
        except Exception as e:
            return {"success": False, "error": f"System control failed: {e}"}

    async def _get_system_metrics(self, params: GetSystemMetricsParams) -> dict[str, object]:
        """Query Prometheus metrics"""
        if get_system_metrics is None:
            return {"error": "Performance tools not available (Import failed)"}
        return cast(dict[str, object], await get_system_metrics(params.window))
