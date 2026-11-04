from typing import Any

"""Legacy compatibility Agency Backend Architect agent."""


class AgencyBackendArchitectAgent:
    """Compatibility agent used by legacy e2e tests."""

    def __init__(
        self, agent_id: str = "agency_backend_architect", tenant_id: int = 1
    ) -> None:
        self.agent_id = agent_id
        self.tenant_id = tenant_id
