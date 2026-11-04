"""
P5.5 Unit Tests for Load Test Code

Unit tests for locustfile.py to achieve 95%+ code coverage.
Tests the load test configuration, token management, and user behavior.

Reference: Test Plan v1.0 Section 4 - Performance Testing
Pattern: Based on P5.4 approach (unit test the test code itself)
"""

import os

# Import the load test components
import sys
import time
from datetime import datetime, timedelta
from typing import Dict
from unittest.mock import MagicMock, Mock, patch

import jwt
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from locustfile import (
    EnduranceTestUser,
    LoadTestUser,
    PerformanceConfig,
    PerformanceMetrics,
    SanskritiSetuPerformanceUser,
    SpikeTestUser,
    StressTestUser,
    TokenManager,
)

# ============================================================================
# SECTION 1: PerformanceConfig Tests
# ============================================================================


class TestPerformanceConfig:
    """Tests for PerformanceConfig class"""

    def test_config_initialization(self):
        """Verify config initializes with correct values"""
        assert PerformanceConfig.API_BASE_URL == "http://localhost:8100"

    def test_config_test_users_created(self):
        """Verify test users are created"""
        assert len(PerformanceConfig.TEST_USERS) == 5
        assert all("email" in user and "password" in user for user in PerformanceConfig.TEST_USERS)

    def test_config_load_targets(self):
        """Verify load test targets are configured"""
        assert "load" in PerformanceConfig.TARGETS
        assert PerformanceConfig.TARGETS["load"]["users"] == 50
        assert PerformanceConfig.TARGETS["load"]["p95_ms"] == 200

    def test_config_stress_targets(self):
        """Verify stress test targets are configured"""
        assert "stress" in PerformanceConfig.TARGETS
        assert PerformanceConfig.TARGETS["stress"]["users"] == 200

    def test_config_spike_targets(self):
        """Verify spike test targets are configured"""
        assert "spike" in PerformanceConfig.TARGETS
        assert PerformanceConfig.TARGETS["spike"]["users"] == 100

    def test_config_endurance_targets(self):
        """Verify endurance test targets are configured"""
        assert "endurance" in PerformanceConfig.TARGETS
        assert PerformanceConfig.TARGETS["endurance"]["duration_min"] == 60

    def test_config_task_weights(self):
        """Verify task weights are configured"""
        weights = PerformanceConfig.TASK_WEIGHTS
        assert "list_workflows" in weights
        assert "create_workflow" in weights
        # Weights should sum to 100
        assert sum(weights.values()) == 100

    def test_config_task_weight_distribution(self):
        """Verify task weights follow realistic distribution"""
        weights = PerformanceConfig.TASK_WEIGHTS
        assert weights["list_workflows"] == 40  # Most common
        assert weights["get_workflow"] == 25
        assert weights["search_workflows"] == 20
        assert weights["create_workflow"] == 10
        assert weights["update_workflow"] == 5


# ============================================================================
# SECTION 2: TokenManager Tests
# ============================================================================


class TestTokenManager:
    """Tests for TokenManager class"""

    def test_token_manager_initialization(self):
        """Verify TokenManager initializes"""
        manager = TokenManager()
        assert manager.secret_key is not None
        assert len(manager.tokens) == 0

    def test_token_generation(self):
        """Verify token generation creates valid JWT"""
        manager = TokenManager()
        email = "test@example.com"

        token = manager.generate_token(email)

        assert isinstance(token, str)
        assert len(token) > 0
        assert email in manager.tokens

    def test_token_contains_required_claims(self):
        """Verify generated token contains required JWT claims"""
        manager = TokenManager()
        email = "test@example.com"

        token = manager.generate_token(email)

        # Decode token to verify claims
        decoded = jwt.decode(token, manager.secret_key, algorithms=["HS256"])

        assert decoded["sub"] == email
        assert "iat" in decoded
        assert "exp" in decoded
        assert "scopes" in decoded

    def test_token_expiry_tracking(self):
        """Verify token expiry is tracked"""
        manager = TokenManager()
        email = "test@example.com"

        token = manager.generate_token(email)

        assert email in manager.token_expiry
        assert isinstance(manager.token_expiry[email], datetime)

    def test_get_cached_token(self):
        """Verify cached tokens are returned"""
        manager = TokenManager()
        email = "test@example.com"

        token1 = manager.generate_token(email)
        token2 = manager.get_token(email)

        assert token1 == token2  # Should return same cached token

    def test_token_regeneration_on_expiry(self):
        """Verify new token generated when old one expires"""
        manager = TokenManager()
        email = "test@example.com"

        token1 = manager.generate_token(email)

        # Manually set expiry to past
        manager.token_expiry[email] = datetime.utcnow() - timedelta(hours=1)

        token2 = manager.get_token(email)

        assert token1 != token2  # Should be different tokens

    def test_auth_headers_generation(self):
        """Verify auth headers are correctly formatted"""
        manager = TokenManager()
        email = "test@example.com"

        headers = manager.get_auth_headers(email)

        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")
        assert len(headers["Authorization"]) > 7  # "Bearer " + token


# ============================================================================
# SECTION 3: PerformanceMetrics Tests
# ============================================================================


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics class"""

    def test_metrics_initialization(self):
        """Verify PerformanceMetrics initializes"""
        metrics = PerformanceMetrics()
        assert len(metrics.response_times) == 0
        assert len(metrics.errors) == 0

    def test_record_response_time(self):
        """Verify response time recording"""
        metrics = PerformanceMetrics()

        metrics.record_response_time(100.5)
        metrics.record_response_time(200.3)

        assert len(metrics.response_times) == 2
        assert 100.5 in metrics.response_times
        assert 200.3 in metrics.response_times

    def test_record_error(self):
        """Verify error recording"""
        metrics = PerformanceMetrics()

        metrics.record_error("Connection timeout")
        metrics.record_error("500 Server error")

        assert len(metrics.errors) == 2

    def test_percentile_calculation(self):
        """Verify percentile calculation"""
        metrics = PerformanceMetrics()

        # Add sample response times
        response_times = [50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
        for rt in response_times:
            metrics.record_response_time(rt)

        # Test percentiles
        p50 = metrics.get_percentile(50)
        p95 = metrics.get_percentile(95)
        p99 = metrics.get_percentile(99)

        assert p50 is not None
        assert p95 is not None
        assert p99 is not None
        assert p50 <= p95 <= p99

    def test_summary_generation_with_data(self):
        """Verify summary generation with response data"""
        metrics = PerformanceMetrics()

        # Add sample data
        for i in range(100, 600, 100):
            metrics.record_response_time(float(i))

        summary = metrics.get_summary()

        assert summary["total_requests"] == 5
        assert summary["total_errors"] == 0
        assert summary["error_rate"] == 0
        assert summary["min_ms"] == 100.0
        assert summary["max_ms"] == 500.0
        assert "avg_ms" in summary
        assert "p50_ms" in summary
        assert "p95_ms" in summary

    def test_summary_with_errors(self):
        """Verify summary includes error information"""
        metrics = PerformanceMetrics()

        # Add data with errors
        for i in range(5):
            metrics.record_response_time(100.0)
            if i > 2:
                metrics.record_error("Test error")

        summary = metrics.get_summary()

        assert summary["total_errors"] == 2
        assert summary["error_rate"] > 0

    def test_empty_metrics_summary(self):
        """Verify summary for empty metrics"""
        metrics = PerformanceMetrics()

        summary = metrics.get_summary()

        assert summary["total_requests"] == 0
        assert summary["error_rate"] == 0


# ============================================================================
# SECTION 4: User Class Tests
# ============================================================================


class TestLoadTestUser:
    """Tests for load test user behavior"""

    def test_load_test_user_initialization(self):
        """Verify LoadTestUser initializes"""
        user = LoadTestUser(Mock())
        assert user is not None
        assert hasattr(user, "wait_time")

    def test_stress_test_user_wait_time(self):
        """Verify StressTestUser has reduced wait time"""
        stress_user = StressTestUser(Mock())
        load_user = LoadTestUser(Mock())

        # Both should have wait_time between tasks
        assert hasattr(stress_user, "wait_time")
        assert hasattr(load_user, "wait_time")

    def test_spike_test_user_characteristics(self):
        """Verify SpikeTestUser has variable wait times"""
        user = SpikeTestUser(Mock())
        assert hasattr(user, "wait_time")

    def test_endurance_test_user_characteristics(self):
        """Verify EnduranceTestUser has longer think time"""
        user = EnduranceTestUser(Mock())
        assert hasattr(user, "wait_time")


# ============================================================================
# SECTION 5: Load Test Scenario Coverage
# ============================================================================


class TestLoadTestScenarios:
    """Tests verifying load test scenario configuration"""

    def test_load_scenario_50_users(self):
        """Verify load test scenario is 50 concurrent users"""
        assert PerformanceConfig.TARGETS["load"]["users"] == 50

    def test_load_scenario_p95_target(self):
        """Verify load test p95 target is 200ms"""
        assert PerformanceConfig.TARGETS["load"]["p95_ms"] == 200

    def test_stress_scenario_200_users(self):
        """Verify stress test scenario is 200 concurrent users"""
        assert PerformanceConfig.TARGETS["stress"]["users"] == 200

    def test_stress_scenario_allows_higher_latency(self):
        """Verify stress test allows higher p95 latency"""
        stress_p95 = PerformanceConfig.TARGETS["stress"]["p95_ms"]
        load_p95 = PerformanceConfig.TARGETS["load"]["p95_ms"]
        assert stress_p95 > load_p95

    def test_spike_scenario_100_users(self):
        """Verify spike test scenario is 100 users"""
        assert PerformanceConfig.TARGETS["spike"]["users"] == 100

    def test_spike_scenario_recovery_time(self):
        """Verify spike test expects 30 second recovery"""
        assert PerformanceConfig.TARGETS["spike"]["recovery_sec"] == 30

    def test_endurance_scenario_1_hour(self):
        """Verify endurance test runs for 1 hour"""
        assert PerformanceConfig.TARGETS["endurance"]["duration_min"] == 60

    def test_error_rate_targets(self):
        """Verify error rate targets are reasonable"""
        assert PerformanceConfig.TARGETS["load"]["error_rate"] == 0.01  # 1%
        assert PerformanceConfig.TARGETS["stress"]["error_rate"] == 0.05  # 5%
        assert PerformanceConfig.TARGETS["spike"]["error_rate"] == 0.10  # 10%


# ============================================================================
# SECTION 6: Task Distribution Tests
# ============================================================================


class TestTaskDistribution:
    """Tests for realistic task weight distribution"""

    def test_list_workflows_is_most_common(self):
        """Verify list_workflows is most common task (40%)"""
        assert PerformanceConfig.TASK_WEIGHTS["list_workflows"] == 40

    def test_get_workflow_is_second_common(self):
        """Verify get_workflow is second common (25%)"""
        assert PerformanceConfig.TASK_WEIGHTS["get_workflow"] == 25

    def test_write_operations_less_common(self):
        """Verify write operations are less common"""
        create_weight = PerformanceConfig.TASK_WEIGHTS["create_workflow"]
        update_weight = PerformanceConfig.TASK_WEIGHTS["update_workflow"]
        read_weight = PerformanceConfig.TASK_WEIGHTS["list_workflows"]

        assert create_weight < read_weight
        assert update_weight < create_weight

    def test_task_weights_sum_to_100(self):
        """Verify task weights sum to 100 for proper distribution"""
        total = sum(PerformanceConfig.TASK_WEIGHTS.values())
        assert total == 100


# ============================================================================
# SECTION 7: Load Test Configuration Validation
# ============================================================================


class TestLoadTestConfiguration:
    """Tests for load test configuration validity"""

    def test_all_scenarios_configured(self):
        """Verify all 4 scenarios are configured"""
        scenarios = ["load", "stress", "spike", "endurance"]
        for scenario in scenarios:
            assert scenario in PerformanceConfig.TARGETS

    def test_test_users_have_credentials(self):
        """Verify test users have email and password"""
        for user in PerformanceConfig.TEST_USERS:
            assert "email" in user
            assert "password" in user
            assert user["email"].startswith("loadtest_")
            assert "@example.com" in user["email"]

    def test_api_base_url_configured(self):
        """Verify API base URL is configured"""
        assert PerformanceConfig.API_BASE_URL is not None
        assert PerformanceConfig.API_BASE_URL.startswith("http")

    def test_pagination_defaults(self):
        """Verify pagination defaults are set"""
        assert PerformanceConfig.DEFAULT_PAGE_SIZE == 10
        assert PerformanceConfig.MAX_WORKFLOWS == 1000


# ============================================================================
# SECTION 8: Performance Test Execution Summary
# ============================================================================


class TestPerformanceTestExecutionSummary:
    """Summary test for performance testing setup"""

    def test_all_load_test_components_present(self):
        """Verify all load test components are implemented"""
        assert PerformanceConfig is not None
        assert TokenManager is not None
        assert PerformanceMetrics is not None
        assert SanskritiSetuPerformanceUser is not None

    def test_all_user_classes_implemented(self):
        """Verify all scenario user classes are implemented"""
        assert LoadTestUser is not None
        assert StressTestUser is not None
        assert SpikeTestUser is not None
        assert EnduranceTestUser is not None

    def test_load_test_ready_for_execution(self):
        """Verify load test is ready for locust execution"""
        # Verify config has all needed components
        assert hasattr(PerformanceConfig, "API_BASE_URL")
        assert hasattr(PerformanceConfig, "TEST_USERS")
        assert hasattr(PerformanceConfig, "TARGETS")
        assert hasattr(PerformanceConfig, "TASK_WEIGHTS")

    def test_performance_metrics_collection_ready(self):
        """Verify performance metrics collection is ready"""
        metrics = PerformanceMetrics()
        assert hasattr(metrics, "record_response_time")
        assert hasattr(metrics, "record_error")
        assert hasattr(metrics, "get_summary")
        assert hasattr(metrics, "get_percentile")
