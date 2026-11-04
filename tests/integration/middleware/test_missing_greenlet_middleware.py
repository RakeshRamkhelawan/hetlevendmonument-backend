"""
Integration test for MissingGreenlet regression (B-001 / B-001b).

This test hits real async DB endpoints and verifies that no middleware
raises MissingGreenlet. It requires the full FastAPI app with all middleware.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import create_app


@pytest.mark.integration
class TestMissingGreenletRegression:
    async def test_board_queue_no_missing_greenlet(self) -> None:
        """
        Regression: /api/v1/board/queue was returning 500 due to MissingGreenlet
        caused by AuditLoggingMiddleware (BaseHTTPMiddleware + async DB calls).
        """
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # This endpoint requires auth; we expect 401, NOT 500
            response = await client.get("/api/v1/board/queue")

        # 401 = auth required (expected)
        # 500 = MissingGreenlet or other server error (NOT expected)
        assert response.status_code != 500, (
            f"Server error on /api/v1/board/queue: {response.text}"
        )

    async def test_copilot_tasks_no_missing_greenlet(self) -> None:
        """
        Regression: /api/v1/copilot/tasks was also affected by MissingGreenlet.
        """
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/copilot/tasks")

        assert response.status_code != 500, (
            f"Server error on /api/v1/copilot/tasks: {response.text}"
        )

    async def test_agents_post_no_missing_greenlet(self) -> None:
        """
        Regression: POST endpoints with RateLimitMiddleware + DB calls.
        """
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/agents", json={"name": "test"})

        # We expect 401 (no auth) or 422 (validation), but NEVER 500
        assert response.status_code != 500, (
            f"Server error on POST /api/v1/agents: {response.text}"
        )
