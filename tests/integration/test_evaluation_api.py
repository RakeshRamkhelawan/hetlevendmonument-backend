"""
Integration Tests for Evaluation API
"""

import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from src.core.api.search_endpoints import get_current_tenant_id
from src.core.auth.dependencies import get_current_user_id
from src.core.config.unified_config import config
from src.main import app

pytestmark = pytest.mark.skip(
    reason="Evaluation API contract changed; integration tests need refresh"
)


def create_test_token(user_id: str, tenant_id: int):
    # Ensure iat is in the past to avoid 'not yet valid' error
    now = datetime.now(timezone.utc)
    payload = {
        "sub": f"user_{user_id}",
        "user_id": user_id,
        "tenant_id": tenant_id,
        "security_level": "authenticated",
        "iat": now - timedelta(minutes=5),
        "exp": now + timedelta(hours=1),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, config.jwt_secret_key, algorithm=config.jwt_algorithm)


@pytest.fixture
def test_token():
    return create_test_token("eval_user", 1)


@pytest.fixture
async def setup_db(postgres_engine):
    from src.core.database.database import Base

    async with postgres_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


class TestEvaluationAPI:
    @pytest.mark.asyncio
    async def test_trigger_evaluation_success(self, test_token, setup_db):
        app.dependency_overrides[get_current_user_id] = lambda: 1
        app.dependency_overrides[get_current_tenant_id] = lambda: 1

        mock_eval_run = MagicMock()
        mock_eval_run.id = 1
        mock_eval_run.tenant_id = 1
        mock_eval_run.query = "test"
        mock_eval_run.response = "test"
        mock_eval_run.retrieved_contexts = ["test"]
        mock_eval_run.timestamp = datetime.now(timezone.utc)
        mock_eval_run.metrics.faithfulness = 0.9
        mock_eval_run.metrics.precision = 0.8
        mock_eval_run.metrics.recall = 0.7
        mock_eval_run.metrics.context_precision = 0.95
        mock_eval_run.metrics.latency_ms = 100.0
        mock_eval_run.metadata = {}

        # Use patch string that matches the class being used by middleware
        with patch(
            "src.core.security.security_manager.ProductionSecurityManager.verify_token"
        ) as mock_verify:
            mock_verify.return_value = {
                "sub": "eval_user",
                "tenant_id": 1,
                "user_id": "eval_user",
                "security_level": "authenticated",
            }
            with patch(
                "src.core.evaluation.evaluation_service.evaluation_service.evaluate_rag_response",
                return_value=mock_eval_run,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    response = await ac.post(
                        "/api/v1/evaluation/evaluate",
                        json={
                            "query": "What is Sanskrit?",
                            "response": "An ancient language.",
                            "contexts": ["Sanskrit is an ancient Indo-Aryan language."],
                        },
                        headers={"Authorization": f"Bearer {test_token}"},
                    )

        app.dependency_overrides.clear()
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["metrics"]["faithfulness"] == 0.9

    @pytest.mark.asyncio
    async def test_get_stats_success(self, test_token, setup_db):
        app.dependency_overrides[get_current_tenant_id] = lambda: 1

        mock_stats = {
            "tenant_id": 1,
            "total_runs": 5,
            "avg_faithfulness": 0.85,
            "avg_precision": 0.8,
            "avg_recall": 0.75,
            "avg_context_precision": 0.9,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        with patch(
            "src.core.security.security_manager.ProductionSecurityManager.verify_token"
        ) as mock_verify:
            mock_verify.return_value = {
                "sub": "eval_user",
                "tenant_id": 1,
                "user_id": "eval_user",
                "security_level": "authenticated",
            }
            with patch(
                "src.core.evaluation.evaluation_service.evaluation_service.get_tenant_stats",
                return_value=mock_stats,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    response = await ac.get(
                        "/api/v1/evaluation/stats",
                        headers={"Authorization": f"Bearer {test_token}"},
                    )

        app.dependency_overrides.clear()
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["avg_faithfulness"] == 0.85
