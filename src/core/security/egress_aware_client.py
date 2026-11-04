"""
Egress-aware HTTP client wrapper.

Validates all outbound requests against EgressController policy before
allowing them through. Raises EgressBlockedError if the policy denies.

Audit logging is wrapped in best_effort so egress validation never
fails the primary request due to logging issues.
"""

from __future__ import annotations

from typing import Any

import httpx

from src.core.exceptions.exceptions import EgressBlockedError
from src.core.security.egress_control import EgressController, EgressDecision
from src.core.utils.best_effort import best_effort


class EgressAwareAsyncClient:
    """Wraps httpx.AsyncClient with egress policy validation.

    Usage:
        async with EgressAwareAsyncClient(
            egress_controller=controller,
            tenant_id=1,
            agent_id="my_agent",
        ) as client:
            response = await client.get("https://example.com/api")
    """

    def __init__(
        self,
        egress_controller: EgressController,
        tenant_id: int,
        agent_id: str | None = None,
        **httpx_kwargs: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self._egress = egress_controller
        self._tenant_id = tenant_id
        self._agent_id = agent_id
        self._client = httpx.AsyncClient(**httpx_kwargs)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send HTTP request after egress validation."""
        content = kwargs.get("content", b"")
        if content is None:
            content = b""
        request_size = (
            len(content)
            if isinstance(content, bytes)
            else len(content.encode("utf-8"))
            if isinstance(content, str)
            else 0
        )

        result = await self._egress.validate_request(
            url=url,
            tenant_id=self._tenant_id,
            agent_id=self._agent_id,
            request_size=request_size,
        )

        if result.decision != EgressDecision.ALLOW:
            raise EgressBlockedError(
                url=url,
                reason=result.reason or "Egress policy denied",
                tenant_id=self._tenant_id,
            )

        return await self._client.request(method, url, **kwargs)

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)

    async def __aenter__(self) -> EgressAwareAsyncClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self._client.aclose()
