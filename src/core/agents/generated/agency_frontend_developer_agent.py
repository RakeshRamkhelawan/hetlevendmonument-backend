from typing import Any

"""Legacy compatibility Agency Frontend Developer agent."""


class AgencyFrontendDeveloperAgent:
    """Compatibility agent used by legacy e2e tests."""

    def __init__(
        self, agent_id: str = "agency_frontend_developer", tenant_id: int = 1
    ) -> None:
        self.agent_id = agent_id
        self.tenant_id = tenant_id
