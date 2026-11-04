# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/subagents/ (SP-API-007)
from src.core.api.v1.subagents.router import (  # noqa: F401
    discover_agents,
    get_agent_status,
    instantiate_agent,
    list_agents,
    load_agents,
    router,
)
from src.core.api.v1.subagents.schemas import (  # noqa: F401
    AgentActionRequest,
    AgentInstantiateRequest,
    AgentLoadRequest,
)
