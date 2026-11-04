"""
Unit tests for AI Quality Collectors - Slice 3

Tests AI quality metric collection and alerting.
Sprint 4 - S4.3: AI quality metric collectors
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest


TEST_TENANT_ID = 42


@pytest.fixture
def mock_db_session():
    """Mock database session for testing."""
    session = AsyncMock()
    session.add = Mock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_repository(mock_db_session):
    """Mock AIQualityEventRepository."""
    from src.core.procedures.ai_quality_repository import AIQualityEventRepository

    repo = AIQualityEventRepository(mock_db_session, tenant_id=TEST_TENANT_ID)
    repo.record_event = AsyncMock()
    return repo


class TestAIQualityCollector:
    """Test suite for AI quality metrics collection."""

    @pytest.mark.asyncio
    async def test_calculate_match_accuracy(self, mock_db_session, mock_repository):
        """Calculate ratio of auto-selected vs user-override procedures."""
        from src.core.ai_quality.collectors import AIQualityCollector

        collector = AIQualityCollector(mock_db_session, tenant_id=TEST_TENANT_ID)

        # Mock execution history: 8 auto-selected, 2 user-overridden
        executions = [{"procedure_id": f"proc_{i}", "auto_selected": i < 8} for i in range(10)]

        accuracy = collector.calculate_match_accuracy(executions)

        # Accuracy should be 8/10 = 0.8 (80%)
        assert accuracy == pytest.approx(0.8, abs=0.01)

    @pytest.mark.asyncio
    async def test_calculate_match_accuracy_perfect(self, mock_db_session):
        """Test perfect accuracy (100%)."""
        from src.core.ai_quality.collectors import AIQualityCollector

        collector = AIQualityCollector(mock_db_session, tenant_id=TEST_TENANT_ID)

        # All auto-selected
        executions = [{"procedure_id": f"proc_{i}", "auto_selected": True} for i in range(10)]

        accuracy = collector.calculate_match_accuracy(executions)
        assert accuracy == 1.0

    @pytest.mark.asyncio
    async def test_calculate_match_accuracy_zero(self, mock_db_session):
        """Test zero accuracy (all user overrides)."""
        from src.core.ai_quality.collectors import AIQualityCollector

        collector = AIQualityCollector(mock_db_session, tenant_id=TEST_TENANT_ID)

        # All user-overridden
        executions = [{"procedure_id": f"proc_{i}", "auto_selected": False} for i in range(10)]

        accuracy = collector.calculate_match_accuracy(executions)
        assert accuracy == 0.0

    @pytest.mark.asyncio
    async def test_record_hallucination_event(self, mock_db_session, mock_repository):
        """Match on deleted procedure should count as hallucination."""
        from src.core.ai_quality.collectors import AIQualityCollector
        from src.core.procedures.schemas import AIQualityEventCreate

        collector = AIQualityCollector(mock_db_session, tenant_id=TEST_TENANT_ID)
        collector.repository = mock_repository

        execution_id = uuid4()

        await collector.record_hallucination(
            execution_id=execution_id,
            procedure_id="deleted_proc_123",
            details={"reason": "matched_deleted_procedure", "query": "approve invoice"},
        )

        # Verify repository.record_event was called with correct event type
        mock_repository.record_event.assert_called_once()
        call_args = mock_repository.record_event.call_args[0][0]

        assert isinstance(call_args, AIQualityEventCreate)
        assert call_args.execution_id == execution_id
        assert call_args.event_type == "hallucination"
        assert call_args.severity == "error"
        assert "matched_deleted_procedure" in call_args.details.get("reason", "")

    @pytest.mark.asyncio
    async def test_quality_alert_trigger(self, mock_db_session):
        """If accuracy < 0.90, trigger alert logic."""
        from src.core.ai_quality.collectors import AIQualityCollector

        collector = AIQualityCollector(mock_db_session, tenant_id=TEST_TENANT_ID)

        # Mock 75% accuracy (below threshold)
        executions = [{"procedure_id": f"proc_{i}", "auto_selected": i < 75} for i in range(100)]

        accuracy = collector.calculate_match_accuracy(executions)
        assert accuracy == 0.75

        # Check if alert should trigger
        should_alert = collector.should_trigger_alert(accuracy, threshold=0.90)
        assert should_alert is True

        # Test above threshold (no alert)
        should_alert = collector.should_trigger_alert(0.95, threshold=0.90)
        assert should_alert is False

    @pytest.mark.asyncio
    async def test_persists_event_in_aiqualityevents_table(self, mock_db_session):
        """Verify that quality event results in DB insert with correct FK."""
        from src.core.ai_quality.collectors import AIQualityCollector
        from src.core.procedures.models import AIQualityEvent

        collector = AIQualityCollector(mock_db_session, tenant_id=TEST_TENANT_ID)

        execution_id = uuid4()

        # Record a low confidence event
        await collector.record_event(
            execution_id=execution_id,
            event_type="low_confidence",
            severity="warning",
            details={"confidence": 0.45, "threshold": 0.70},
        )

        # Verify session.add was called with AIQualityEvent
        mock_db_session.add.assert_called_once()
        added_event = mock_db_session.add.call_args[0][0]

        assert isinstance(added_event, AIQualityEvent)
        assert added_event.execution_id == execution_id
        assert added_event.event_type == "low_confidence"
        assert added_event.severity == "warning"
        assert added_event.details["confidence"] == 0.45

    @pytest.mark.asyncio
    async def test_updates_prometheus_metrics(self, mock_db_session):
        """Recording events should update Prometheus metrics."""
        from src.core.ai_quality.collectors import AIQualityCollector

        with patch(
            "src.core.ai_quality.collectors.AI_INTENT_MATCH_ACCURACY"
        ) as mock_accuracy_metric:
            with patch(
                "src.core.ai_quality.collectors.AI_HALLUCINATION_RATE"
            ) as mock_hallucination_metric:
                collector = AIQualityCollector(mock_db_session, tenant_id=TEST_TENANT_ID)

                # Update accuracy metric
                collector.update_metrics(tenant_id=1, accuracy=0.92, hallucination_rate=0.02)

                # Verify Prometheus metrics were updated
                mock_accuracy_metric.labels.assert_called_with(tenant_id=1)
                mock_hallucination_metric.labels.assert_called_with(tenant_id=1)

    @pytest.mark.asyncio
    async def test_user_override_tracking(self, mock_db_session, mock_repository):
        """Track when user overrides AI suggestion."""
        from src.core.ai_quality.collectors import AIQualityCollector

        collector = AIQualityCollector(mock_db_session, tenant_id=TEST_TENANT_ID)
        collector.repository = mock_repository

        execution_id = uuid4()

        await collector.record_user_override(
            execution_id=execution_id,
            suggested_procedure="invoice.approval.automated",
            selected_procedure="invoice.approval.manual",
            reason="user_preference",
        )

        # Verify event was recorded
        mock_repository.record_event.assert_called_once()
        call_args = mock_repository.record_event.call_args[0][0]

        assert call_args.event_type == "user_override"
        assert call_args.severity == "info"
        assert "suggested_procedure" in call_args.details

    @pytest.mark.asyncio
    async def test_batch_quality_analysis(self, mock_db_session):
        """Analyze quality metrics for a batch of executions."""
        from src.core.ai_quality.collectors import AIQualityCollector

        collector = AIQualityCollector(mock_db_session, tenant_id=TEST_TENANT_ID)

        # Mock 100 executions
        executions = [
            {
                "execution_id": uuid4(),
                "auto_selected": i < 85,  # 85% accuracy
                "had_hallucination": i >= 95,  # 5% hallucination rate
                "confidence": 0.7 + (i % 30) / 100,  # varying confidence
            }
            for i in range(100)
        ]

        metrics = collector.analyze_batch(executions, tenant_id=1)

        assert metrics["accuracy"] == pytest.approx(0.85, abs=0.01)
        assert metrics["hallucination_rate"] == pytest.approx(0.05, abs=0.01)
        assert metrics["avg_confidence"] > 0.7
        assert metrics["total_executions"] == 100
