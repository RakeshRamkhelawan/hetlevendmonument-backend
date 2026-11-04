"""
F4 self-healing stub audit fixes.

Covers three concrete misleading claims:
1. RepairPlan always used RepairStrategy.RESTART regardless of failure type
2. /healing/status returned repairs_in_progress=1 whenever monitoring_active=True
3. /health claimed "autonomy_level": "full" while all systems are stubs
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.autonomy.self_healing_system import (
    FailureType,
    RepairPlan,
    RepairStrategy,
    SelfHealingSystem,
    SystemFailure,
)

# ---------------------------------------------------------------------------
# 1. RepairPlan strategy mapping
# ---------------------------------------------------------------------------


class TestRepairStrategyMapping:
    """RepairPlan.strategy must reflect the failure type, not always RESTART."""

    def _make_failure(self, failure_type: FailureType) -> SystemFailure:
        return SystemFailure(
            failure_id="f1",
            failure_type=failure_type,
            component="test_component",
            severity=5,
            timestamp=datetime.now(timezone.utc),
            description="test",
        )

    def _run(self, coro):  # type: ignore[no-untyped-def]
        return asyncio.run(coro)

    def test_agent_crash_uses_restart(self) -> None:
        system = SelfHealingSystem()
        failure = self._make_failure(FailureType.AGENT_CRASH)
        plan = self._run(system.detect_and_diagnose_failure(failure))
        assert plan.strategy == RepairStrategy.RESTART

    def test_data_corruption_uses_rollback(self) -> None:
        system = SelfHealingSystem()
        failure = self._make_failure(FailureType.DATA_CORRUPTION)
        plan = self._run(system.detect_and_diagnose_failure(failure))
        assert (
            plan.strategy == RepairStrategy.ROLLBACK
        ), f"DATA_CORRUPTION should map to ROLLBACK, got {plan.strategy}"

    def test_security_breach_uses_manual(self) -> None:
        system = SelfHealingSystem()
        failure = self._make_failure(FailureType.SECURITY_BREACH)
        plan = self._run(system.detect_and_diagnose_failure(failure))
        assert (
            plan.strategy == RepairStrategy.MANUAL
        ), f"SECURITY_BREACH should map to MANUAL, got {plan.strategy}"

    def test_resource_exhaustion_uses_rollback(self) -> None:
        system = SelfHealingSystem()
        failure = self._make_failure(FailureType.RESOURCE_EXHAUSTION)
        plan = self._run(system.detect_and_diagnose_failure(failure))
        assert plan.strategy == RepairStrategy.ROLLBACK

    def test_integration_failure_uses_replace(self) -> None:
        system = SelfHealingSystem()
        failure = self._make_failure(FailureType.INTEGRATION_FAILURE)
        plan = self._run(system.detect_and_diagnose_failure(failure))
        assert plan.strategy == RepairStrategy.REPLACE

    def test_performance_degradation_uses_patch(self) -> None:
        system = SelfHealingSystem()
        failure = self._make_failure(FailureType.PERFORMANCE_DEGRADATION)
        plan = self._run(system.detect_and_diagnose_failure(failure))
        assert plan.strategy == RepairStrategy.PATCH

    def test_configuration_error_uses_patch(self) -> None:
        system = SelfHealingSystem()
        failure = self._make_failure(FailureType.CONFIGURATION_ERROR)
        plan = self._run(system.detect_and_diagnose_failure(failure))
        assert plan.strategy == RepairStrategy.PATCH

    def test_dependency_failure_uses_replace(self) -> None:
        system = SelfHealingSystem()
        failure = self._make_failure(FailureType.DEPENDENCY_FAILURE)
        plan = self._run(system.detect_and_diagnose_failure(failure))
        assert plan.strategy == RepairStrategy.REPLACE


# ---------------------------------------------------------------------------
# 2. /healing/status repairs_in_progress uses actual count
# ---------------------------------------------------------------------------


class TestHealingStatusRepairsInProgress:
    """repairs_in_progress must come from the status dict, not from monitoring_active."""

    @pytest.fixture()
    def client(self, client):  # type: ignore[override]
        return client

    def test_repairs_in_progress_zero_when_none_active(self, client, admin_auth_headers):
        with patch("src.core.api.autonomous_endpoints.get_self_healing_system") as mock_healing:
            instance = AsyncMock()
            instance.get_system_status = AsyncMock(
                return_value={
                    "system_status": "healthy",
                    "failure_history_count": 0,
                    "monitoring_active": True,
                    "repairs_in_progress": 0,
                    "repair_history_count": 0,
                    "healing_metrics": {"healing_success_rate": 1.0, "mean_time_to_repair": 0.0},
                    "recent_failures": 0,
                    "registered_components": 0,
                    "emergency_protocols_available": 0,
                    "components": {},
                }
            )
            mock_healing.return_value = instance

            response = client.get("/api/v1/autonomous/healing/status", headers=admin_auth_headers)

            assert response.status_code == 200
            data = response.json()
            # monitoring_active=True should NOT inflate this to 1
            assert (
                data["repairs_in_progress"] == 0
            ), "repairs_in_progress must reflect actual count (0), not monitoring_active flag"

    def test_repairs_in_progress_reflects_actual_count(self, client, admin_auth_headers):
        with patch("src.core.api.autonomous_endpoints.get_self_healing_system") as mock_healing:
            instance = AsyncMock()
            instance.get_system_status = AsyncMock(
                return_value={
                    "system_status": "degraded",
                    "failure_history_count": 2,
                    "monitoring_active": True,
                    "repairs_in_progress": 2,
                    "repair_history_count": 1,
                    "healing_metrics": {"healing_success_rate": 0.5, "mean_time_to_repair": 30.0},
                    "recent_failures": 2,
                    "registered_components": 3,
                    "emergency_protocols_available": 1,
                    "components": {},
                }
            )
            mock_healing.return_value = instance

            response = client.get("/api/v1/autonomous/healing/status", headers=admin_auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data["repairs_in_progress"] == 2


# ---------------------------------------------------------------------------
# 3. /health must NOT claim "autonomy_level": "full"
# ---------------------------------------------------------------------------


class TestAutonomyLevelClaim:
    """The /health endpoint must not assert full autonomy for stub systems."""

    def test_health_does_not_claim_full_autonomy(self, client, admin_auth_headers):
        with (
            patch("src.core.api.autonomous_endpoints.get_agent_factory") as mock_factory,
            patch("src.core.api.autonomous_endpoints.get_self_healing_system") as mock_healing,
            patch("src.core.api.autonomous_endpoints.get_code_generator") as mock_generator,
            patch("src.core.api.autonomous_endpoints.get_emergent_intelligence") as mock_emergence,
        ):
            for mock in (mock_factory, mock_healing, mock_generator, mock_emergence):
                instance = AsyncMock()
                instance.get_system_status = AsyncMock(return_value={"status": "operational"})
                mock.return_value = instance

            response = client.get("/api/v1/autonomous/health", headers=admin_auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert (
                data.get("autonomy_level") != "full"
            ), "autonomy_level must not claim 'full' while systems are stubs"

    def test_health_autonomy_level_is_stub_phase4(self, client, admin_auth_headers):
        with (
            patch("src.core.api.autonomous_endpoints.get_agent_factory") as mock_factory,
            patch("src.core.api.autonomous_endpoints.get_self_healing_system") as mock_healing,
            patch("src.core.api.autonomous_endpoints.get_code_generator") as mock_generator,
            patch("src.core.api.autonomous_endpoints.get_emergent_intelligence") as mock_emergence,
        ):
            for mock in (mock_factory, mock_healing, mock_generator, mock_emergence):
                instance = AsyncMock()
                instance.get_system_status = AsyncMock(return_value={"status": "operational"})
                mock.return_value = instance

            response = client.get("/api/v1/autonomous/health", headers=admin_auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data.get("autonomy_level") == "stub_phase4"
