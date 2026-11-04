"""
Tests for Evaluation Endpoints
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_batch_service():
    """Mock the batch evaluation service"""
    with patch("src.core.api.evaluation_endpoints.batch_evaluation_service") as mock:
        mock.start_batch_evaluation = AsyncMock(
            return_value={
                "id": "test-run-123",
                "name": "Test Run",
                "status": "pending",
                "num_samples": 100,
                "created_at": "2026-03-07T10:00:00Z",
                "metrics": None,
                "error": None,
            }
        )
        mock.list_runs = AsyncMock(
            return_value=[
                {
                    "id": "test-run-123",
                    "name": "Test Run",
                    "status": "completed",
                    "num_samples": 100,
                    "created_at": "2026-03-07T10:00:00Z",
                    "metrics": {
                        "faithfulness": 0.92,
                        "precision": 0.88,
                        "recall": 0.85,
                        "context_precision": 0.90,
                        "answer_relevancy": 0.91,
                    },
                    "error": None,
                }
            ]
        )
        mock.get_run_detail = AsyncMock(
            return_value={
                "id": "test-run-123",
                "name": "Test Run",
                "status": "completed",
                "num_samples": 100,
                "started_at": "2026-03-07T10:00:00Z",
                "completed_at": "2026-03-07T10:05:00Z",
                "metrics": {
                    "faithfulness": 0.92,
                    "precision": 0.88,
                    "recall": 0.85,
                    "context_precision": 0.90,
                    "answer_relevancy": 0.91,
                },
                "results": [],
                "error": None,
            }
        )
        mock.get_stats = AsyncMock(
            return_value={
                "total_runs": 10,
                "completed_runs": 8,
                "failed_runs": 2,
                "avg_faithfulness": 0.92,
                "avg_context_precision": 0.88,
                "avg_answer_relevancy": 0.91,
                "avg_context_recall": 0.85,
                "total_samples_evaluated": 1000,
            }
        )
        yield mock


class TestEvaluationEndpoints:
    """Test suite for evaluation endpoints"""

    def test_start_evaluation(self, client: TestClient, mock_batch_service, auth_headers):
        """Test POST /api/v1/evaluation/evaluate"""
        response = client.post(
            "/api/v1/evaluation/evaluate",
            json={"tenant_id": "1", "num_samples": 100},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "test-run-123"
        assert data["status"] == "pending"
        assert data["num_samples"] == 100

    def test_list_evaluation_runs(self, client: TestClient, mock_batch_service, auth_headers):
        """Test GET /api/v1/evaluation/runs"""
        response = client.get(
            "/api/v1/evaluation/runs",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "test-run-123"
        assert data[0]["status"] == "completed"

    def test_get_evaluation_run_detail(self, client: TestClient, mock_batch_service, auth_headers):
        """Test GET /api/v1/evaluation/results/{run_id}"""
        response = client.get(
            "/api/v1/evaluation/results/test-run-123",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-run-123"
        assert data["status"] == "completed"
        assert "metrics" in data
        assert "results" in data

    def test_get_evaluation_stats(self, client: TestClient, mock_batch_service, auth_headers):
        """Test GET /api/v1/evaluation/stats"""
        response = client.get(
            "/api/v1/evaluation/stats",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_runs"] == 10
        assert data["completed_runs"] == 8
        assert data["failed_runs"] == 2
        assert data["avg_faithfulness"] == 0.92
        assert data["total_samples_evaluated"] == 1000

    def test_get_evaluation_run_not_found(
        self, client: TestClient, mock_batch_service, auth_headers
    ):
        """Test GET /api/v1/evaluation/results/{run_id} with non-existent ID"""
        mock_batch_service.get_run_detail.return_value = None

        response = client.get(
            "/api/v1/evaluation/results/non-existent-id",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_list_runs_with_status_filter(
        self, client: TestClient, mock_batch_service, auth_headers
    ):
        """Test GET /api/v1/evaluation/runs with status filter"""
        response = client.get(
            "/api/v1/evaluation/runs?status=completed",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_runs_with_limit(self, client: TestClient, mock_batch_service, auth_headers):
        """Test GET /api/v1/evaluation/runs with limit parameter"""
        response = client.get(
            "/api/v1/evaluation/runs?limit=10",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
