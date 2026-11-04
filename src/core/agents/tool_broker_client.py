# core/agents/tool_broker_client.py

from typing import Any, Optional, cast

import httpx

from src.core.config import settings


class AgentToolBrokerClient:
    """
    Een asynchrone client voor sub-agenten om veilig te communiceren
    met de centrale ToolBrokerService.
    """

    def __init__(self, base_url: str, auth_token: str | None = None) -> None:
        """
        Initialiseert de client.

        Args:
            base_url: De basis-URL van de Tool Broker Service.
            auth_token: Het JWT-token voor authenticatie.
        """
        self.client = httpx.AsyncClient(base_url=base_url)
        if auth_token:
            self.client.headers["Authorization"] = f"Bearer {auth_token}"

    async def execute_tool(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Roept de Tool Broker aan om een specifieke tool uit te voeren.

        Args:
            tool_name: De naam van de tool die uitgevoerd moet worden.
            payload: De input data voor de tool.

        Returns:
            Het resultaat van de tool-executie.
        """
        try:
            response = await self.client.post(
                "/v1/tools/execute",
                json={"tool_name": tool_name, "payload": payload},
                timeout=getattr(settings, "TOOL_BROKER_SERVICE_TIMEOUT", 30),
            )
            response.raise_for_status()
            # De Tool Broker retourneert een JSON met een "result" sleutel
            return cast(dict[str, Any], cast(dict[str, Any], response.json()).get("result", {}))  # TODO(TYPE): replace Any with concrete type
        except httpx.RequestError as exc:
            # Vangt netwerk/connectie fouten af
            raise ConnectionError(f"Tool Broker service onbereikbaar: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            # Vangt API-fouten af (4xx, 5xx) en geeft de details door
            error_detail = cast(dict[str, Any], exc.response.json()).get(  # TODO(TYPE): replace Any with concrete type
                "detail", exc.response.text
            )
            raise ValueError(
                f"Fout bij aanroepen Tool Broker (status {exc.response.status_code}): {error_detail}"
            ) from exc
