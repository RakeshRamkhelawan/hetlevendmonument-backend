"""Tests for ROI Calculator."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.als.enterprise.roi import ROICalculator, ROIMetrics
from src.core.exceptions import AuthError


class TestROICalculatorHappyPath:
    """Happy path tests for ROI Calculator."""

    @pytest.fixture
    def calculator(self):
        return ROICalculator()

    @pytest.mark.asyncio
    async def test_calculate_pack_roi(self, calculator):
        """Should calculate ROI for a pack execution."""
        pack_id = "finance.monthly_close.001"
        tenant_id = "tenant_123"

        # Mock database results
        mock_data = {
            "total_executions": 10,
            "successful_executions": 9,
            "total_time_saved_minutes": 900,  # 10 runs * 90 min saved
            "estimated_value_eur": 5000,
        }

        with patch.object(calculator, "_get_pack_stats", new_callable=AsyncMock) as mock_stats:
            mock_stats.return_value = mock_data

            roi = await calculator.calculate_pack_roi(pack_id, tenant_id)

        assert roi["pack_id"] == pack_id
        assert roi["tenant_id"] == tenant_id
        assert roi["total_executions"] == 10
        assert roi["success_rate"] == 0.9
        assert roi["total_time_saved_hours"] == 15.0  # 900 / 60
        assert roi["roi_percentage"] > 0

    @pytest.mark.asyncio
    async def test_calculate_supervisor_roi(self, calculator):
        """Should calculate ROI for a supervisor."""
        supervisor_id = "finance.treasury.supervisor"
        tenant_id = "tenant_123"

        with patch.object(
            calculator, "_get_supervisor_stats", new_callable=AsyncMock
        ) as mock_stats:
            mock_stats.return_value = {
                "total_tasks": 100,
                "successful_tasks": 95,
                "avg_execution_time_ms": 500,
                "manual_time_per_task_minutes": 30,
            }

            roi = await calculator.calculate_supervisor_roi(supervisor_id, tenant_id)

        assert roi["supervisor_id"] == supervisor_id
        assert roi["total_tasks"] == 100
        assert roi["success_rate"] == 0.95

    @pytest.mark.asyncio
    async def test_calculate_platform_roi(self, calculator):
        """Should calculate overall platform ROI."""
        tenant_id = "tenant_123"

        with patch.object(calculator, "_get_platform_stats", new_callable=AsyncMock) as mock_stats:
            mock_stats.return_value = {
                "total_packs_executed": 50,
                "total_agents_executed": 200,
                "total_time_saved_hours": 500,
                "operational_cost_eur": 1000,
            }

            roi = await calculator.calculate_platform_roi(tenant_id)

        assert roi["tenant_id"] == tenant_id
        assert roi["total_packs_executed"] == 50
        assert roi["total_time_saved_hours"] == 500
        assert "net_value_eur" in roi

    @pytest.mark.asyncio
    async def test_time_saved_calculation(self, calculator):
        """Should correctly calculate time saved."""
        # Manual time - automated time = saved time
        manual_time = 60  # minutes
        automated_time = 5  # minutes
        executions = 10

        time_saved = calculator._calculate_time_saved(manual_time, automated_time, executions)

        assert time_saved == 550  # (60 - 5) * 10

    @pytest.mark.asyncio
    async def test_roi_percentage_calculation(self, calculator):
        """Should correctly calculate ROI percentage."""
        # ROI = (Gain - Cost) / Cost * 100
        gain = 10000  # EUR
        cost = 2000  # EUR

        roi_percentage = calculator._calculate_roi_percentage(gain, cost)

        assert roi_percentage == 400.0  # (10000 - 2000) / 2000 * 100

    @pytest.mark.asyncio
    async def test_get_dashboard_metrics(self, calculator):
        """Should return dashboard-ready metrics."""
        tenant_id = "tenant_123"

        with patch.object(calculator, "_get_platform_stats", new_callable=AsyncMock) as mock_stats:
            mock_stats.return_value = {
                "total_packs_executed": 100,
                "total_time_saved_hours": 1000,
                "total_value_generated_eur": 50000,
            }

            dashboard = await calculator.get_dashboard_metrics(tenant_id)

        assert "overview" in dashboard
        assert "top_performing_packs" in dashboard
        assert "monthly_trend" in dashboard
        assert "efficiency_metrics" in dashboard


class TestROICalculatorUnhappyPath:
    """Unhappy path tests for ROI Calculator."""

    @pytest.fixture
    def calculator(self):
        return ROICalculator()

    @pytest.mark.asyncio
    async def test_missing_tenant_id_raises_error(self, calculator):
        """Should raise AuthError for missing tenant."""
        with pytest.raises(AuthError):
            await calculator.calculate_pack_roi("pack_001", None)

    @pytest.mark.asyncio
    async def test_unknown_pack_returns_empty(self, calculator):
        """Should handle unknown pack gracefully."""
        with patch.object(calculator, "_get_pack_stats", new_callable=AsyncMock) as mock_stats:
            mock_stats.return_value = None

            roi = await calculator.calculate_pack_roi("unknown_pack", "tenant_123")

        assert roi is None or roi == {}

    @pytest.mark.asyncio
    async def test_zero_cost_handling(self, calculator):
        """Should handle zero cost gracefully."""
        gain = 10000
        cost = 0

        # Should return capped value instead of infinity for JSON serialization
        roi = calculator._calculate_roi_percentage(gain, cost)
        assert roi == 999.99  # Capped at 999.99% for JSON compatibility

    @pytest.mark.asyncio
    async def test_database_error_handling(self, calculator):
        """Should handle database errors gracefully."""
        with patch.object(calculator, "_get_platform_stats", side_effect=Exception("DB Error")):
            roi = await calculator.calculate_platform_roi("tenant_123")

        # Should return fallback/empty data, not crash
        assert roi is not None


class TestROIMetrics:
    """Tests for ROIMetrics model."""

    def test_metrics_creation(self):
        """Should create valid ROIMetrics."""
        metrics = ROIMetrics(
            pack_id="finance.monthly_close.001",
            tenant_id="tenant_123",
            execution_date=datetime.utcnow(),
            time_saved_minutes=90,
            cost_saved_eur=250.0,
            success=True,
        )
        assert metrics.time_saved_minutes == 90
        assert metrics.success is True

    def test_invalid_time_saved_raises_error(self):
        """Should reject negative time saved."""
        with pytest.raises(ValueError):
            ROIMetrics(
                pack_id="test",
                tenant_id="tenant_123",
                execution_date=datetime.utcnow(),
                time_saved_minutes=-10,
            )
