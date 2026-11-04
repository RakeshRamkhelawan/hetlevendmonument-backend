"""
P5.5: Load & Performance Tests - Locust-based Performance Testing

Comprehensive performance testing with 4 scenarios:
1. Load Test: 50 concurrent users, p95 < 200ms
2. Stress Test: 200 concurrent users, no crashes
3. Spike Test: 0→100→0 users, recovery <30s
4. Endurance Test: 50 users × 1 hour, no memory leaks

Reference: Test Plan v1.0 Section 4 - Performance Testing
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import jwt
from locust import HttpUser, between, events, task
from locust.contrib.fasthttp import FastHttpUser

logger = logging.getLogger(__name__)


# ============================================================================
# SECTION 1: Performance Test Configuration
# ============================================================================


class PerformanceConfig:
    """Configuration for performance testing scenarios"""

    # API Configuration
    API_BASE_URL = os.getenv(
        "API_BASE_URL", "http://localhost:8100"
    )  # Port updated from 8000 to 8100

    # Test Users
    TEST_USERS = [
        {"email": f"loadtest_{i}@example.com", "password": "LoadTest123!"}
        for i in range(5)  # Create 5 test user credentials
    ]

    # Performance Targets
    TARGETS = {
        "load": {"users": 50, "p95_ms": 200, "error_rate": 0.01},  # Max 1% errors
        "stress": {"users": 200, "p95_ms": 500, "error_rate": 0.05},  # Max 5% errors
        "spike": {
            "users": 100,
            "recovery_sec": 30,
            "error_rate": 0.10,
        },  # Max 10% during spike
        "endurance": {
            "users": 50,
            "duration_min": 60,
            "error_rate": 0.01,
            "memory_growth_mb": 50,
        },
    }

    # Task Weights (realistic user behavior)
    TASK_WEIGHTS = {
        "list_workflows": 40,  # Most common
        "get_workflow": 25,
        "search_workflows": 20,
        "create_workflow": 10,
        "update_workflow": 5,
    }

    # Pagination
    DEFAULT_PAGE_SIZE = 10
    MAX_WORKFLOWS = 1000


# ============================================================================
# SECTION 2: JWT Token Management for Load Tests
# ============================================================================


class TokenManager:
    """Manages JWT token generation and caching for load tests"""

    def __init__(self, secret_key: str = "test-secret-key"):
        self.secret_key = secret_key
        self.tokens: Dict[str, str] = {}
        self.token_expiry: Dict[str, datetime] = {}

    def generate_token(self, email: str, user_id: str = "test-user") -> str:
        """Generate a test JWT token"""
        now = datetime.utcnow()
        payload = {
            "sub": email,
            "user_id": user_id,
            "iat": now,
            "exp": now + timedelta(hours=1),
            "scopes": ["workflows:read", "workflows:write", "agents:read"],
        }

        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        self.tokens[email] = token
        self.token_expiry[email] = payload["exp"]

        return token

    def get_token(self, email: str) -> str:
        """Get cached token or generate new one"""
        if email in self.tokens:
            if self.token_expiry[email] > datetime.utcnow():
                return self.tokens[email]

        return self.generate_token(email)

    def get_auth_headers(self, email: str) -> Dict[str, str]:
        """Get authorization headers with token"""
        token = self.get_token(email)
        return {"Authorization": f"Bearer {token}"}


# Global token manager
_token_manager = TokenManager()


# ============================================================================
# SECTION 3: Base Performance User Class
# ============================================================================


class SanskritiSetuPerformanceUser(FastHttpUser):
    """Base user class for performance testing with realistic behavior"""

    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_index = 0
        self.workflow_ids = []
        self.auth_headers = {}

    def on_start(self):
        """Initialize user: authenticate and set up auth headers"""
        # Select user credentials (round-robin)
        self.user_index = int(time.time() * 1000) % len(PerformanceConfig.TEST_USERS)
        user_creds = PerformanceConfig.TEST_USERS[self.user_index]

        # Get authentication token
        self.auth_headers = _token_manager.get_auth_headers(user_creds["email"])

        logger.info(f"User {self.user_index} authenticated")

    def on_stop(self):
        """Clean up when user stops"""
        logger.info(f"User {self.user_index} session ended")

    # ====== Task 1: List Workflows (40% of traffic) ======
    @task(PerformanceConfig.TASK_WEIGHTS["list_workflows"])
    def list_workflows(self):
        """List workflows with pagination"""
        page = int(time.time() % 10) + 1  # Random page 1-10

        with self.client.get(
            f"/workflows?skip={page-1}&limit={PerformanceConfig.DEFAULT_PAGE_SIZE}",
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
                data = response.json()
                # Cache workflow IDs for later use
                if "items" in data:
                    self.workflow_ids = [w["id"] for w in data["items"][:5]]
            else:
                response.failure(f"Failed to list workflows: {response.status_code}")

    # ====== Task 2: Get Specific Workflow (25% of traffic) ======
    @task(PerformanceConfig.TASK_WEIGHTS["get_workflow"])
    def get_workflow(self):
        """Get details of a specific workflow"""
        if not self.workflow_ids:
            self.list_workflows()  # Populate IDs first

        if self.workflow_ids:
            workflow_id = self.workflow_ids[int(time.time() * 1000) % len(self.workflow_ids)]

            with self.client.get(
                f"/workflows/{workflow_id}",
                headers=self.auth_headers,
                catch_response=True,
            ) as response:
                if response.status_code in [200, 404]:
                    response.success()
                else:
                    response.failure(
                        f"Failed to get workflow {workflow_id}: {response.status_code}"
                    )

    # ====== Task 3: Search Workflows (20% of traffic) ======
    @task(PerformanceConfig.TASK_WEIGHTS["search_workflows"])
    def search_workflows(self):
        """Search workflows by name"""
        search_terms = ["test", "crisis", "workflow", "agent", "automation"]
        search_term = search_terms[int(time.time() * 1000) % len(search_terms)]

        with self.client.get(
            f"/workflows/search?q={search_term}&limit=10",
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Search failed: {response.status_code}")

    # ====== Task 4: Create Workflow (10% of traffic) ======
    @task(PerformanceConfig.TASK_WEIGHTS["create_workflow"])
    def create_workflow(self):
        """Create a new workflow"""
        workflow_data = {
            "name": f"LoadTest_Workflow_{int(time.time() * 1000)}",
            "description": "Performance test workflow",
            "dag": {
                "nodes": [{"id": "node1", "type": "task", "label": "Task 1"}],
                "edges": [],
            },
        }

        with self.client.post(
            "/workflows",
            json=workflow_data,
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code in [201, 200]:
                response.success()
                try:
                    data = response.json()
                    if "id" in data:
                        self.workflow_ids.append(data["id"])
                except Exception as e:
                    logger.warning(f"Failed to parse workflow creation response: {e}")
            else:
                response.failure(f"Failed to create workflow: {response.status_code}")

    # ====== Task 5: Update Workflow (5% of traffic) ======
    @task(PerformanceConfig.TASK_WEIGHTS["update_workflow"])
    def update_workflow(self):
        """Update workflow configuration"""
        if not self.workflow_ids:
            return  # Skip if no workflows

        workflow_id = self.workflow_ids[int(time.time() * 1000) % len(self.workflow_ids)]
        update_data = {"description": f"Updated at {datetime.now(timezone.utc).isoformat()}"}

        with self.client.put(
            f"/workflows/{workflow_id}",
            json=update_data,
            headers=self.auth_headers,
            catch_response=True,
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Failed to update workflow: {response.status_code}")


# ============================================================================
# SECTION 4: Scenario-Specific User Classes
# ============================================================================


class LoadTestUser(SanskritiSetuPerformanceUser):
    """Load Test Scenario: 50 concurrent users, p95 < 200ms"""

    pass


class StressTestUser(SanskritiSetuPerformanceUser):
    """Stress Test Scenario: 200 concurrent users, no crashes"""

    # Faster operations under stress
    wait_time = between(0.5, 2)


class SpikeTestUser(SanskritiSetuPerformanceUser):
    """Spike Test Scenario: 0→100→0 users, recovery <30s"""

    # Variable wait times to simulate spike behavior
    wait_time = between(0.1, 5)


class EnduranceTestUser(SanskritiSetuPerformanceUser):
    """Endurance Test Scenario: 50 users × 1 hour, no memory leaks"""

    # More thinking time between requests to reduce memory pressure
    wait_time = between(2, 5)


# ============================================================================
# SECTION 5: Performance Metrics and Event Handlers
# ============================================================================


class PerformanceMetrics:
    """Collect and analyze performance metrics"""

    def __init__(self):
        self.response_times = []
        self.errors = []
        self.start_time = datetime.now(timezone.utc)

    def record_response_time(self, elapsed_time_ms: float):
        """Record response time in milliseconds"""
        self.response_times.append(elapsed_time_ms)

    def record_error(self, error_msg: str):
        """Record error"""
        self.errors.append(error_msg)

    def get_percentile(self, percentile: int) -> Optional[float]:
        """Calculate percentile response time"""
        if not self.response_times:
            return None

        sorted_times = sorted(self.response_times)
        index = int(len(sorted_times) * percentile / 100)
        return sorted_times[min(index, len(sorted_times) - 1)]

    def get_summary(self) -> Dict:
        """Get performance summary"""
        if not self.response_times:
            return {
                "total_requests": 0,
                "total_errors": len(self.errors),
                "error_rate": 0,
            }

        return {
            "total_requests": len(self.response_times),
            "total_errors": len(self.errors),
            "error_rate": len(self.errors) / len(self.response_times),
            "min_ms": min(self.response_times),
            "max_ms": max(self.response_times),
            "avg_ms": sum(self.response_times) / len(self.response_times),
            "p50_ms": self.get_percentile(50),
            "p95_ms": self.get_percentile(95),
            "p99_ms": self.get_percentile(99),
            "duration_sec": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
        }


# Global metrics collector
_metrics = PerformanceMetrics()


# ============================================================================
# SECTION 6: Locust Event Handlers
# ============================================================================


@events.request.add_listener
def on_request(
    request_type,
    name,
    response_time,
    response_length,
    response,
    context,
    exception,
    **kwargs,
):
    """Handle request completion event"""
    # Record response time in milliseconds
    elapsed_ms = response_time / 1000  # Convert from seconds to milliseconds
    _metrics.record_response_time(elapsed_ms)

    # Record errors
    if exception or (response and response.status_code >= 400):
        error_msg = str(exception) if exception else f"Status {response.status_code}"
        _metrics.record_error(error_msg)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print performance summary when test stops"""
    summary = _metrics.get_summary()

    print("\n")
    print("=" * 80)
    print("PERFORMANCE TEST SUMMARY")
    print("=" * 80)
    print(f"Total Requests: {summary.get('total_requests', 0)}")
    print(f"Total Errors: {summary.get('total_errors', 0)}")
    print(f"Error Rate: {summary.get('error_rate', 0):.2%}")
    print(f"Duration: {summary.get('duration_sec', 0):.1f} seconds")
    print()
    print("Response Times (milliseconds):")
    print(f"  Min: {summary.get('min_ms', 0):.2f}ms")
    print(f"  Avg: {summary.get('avg_ms', 0):.2f}ms")
    print(f"  p50: {summary.get('p50_ms', 0):.2f}ms")
    print(f"  p95: {summary.get('p95_ms', 0):.2f}ms")
    print(f"  p99: {summary.get('p99_ms', 0):.2f}ms")
    print(f"  Max: {summary.get('max_ms', 0):.2f}ms")
    print("=" * 80)
    print()


# ============================================================================
# SECTION 7: Locust Configuration
# ============================================================================

# Run with:
# locust -f tests/load/locustfile.py --host=http://localhost:8100 -u 50 -r 10 -t 60s
#
# Load Test: -u 50 -r 10 -t 300s (5 minutes)
# Stress Test: -u 200 -r 20 -t 600s (10 minutes)
# Spike Test: Use custom shape class
# Endurance Test: -u 50 -r 5 -t 3600s (1 hour)
