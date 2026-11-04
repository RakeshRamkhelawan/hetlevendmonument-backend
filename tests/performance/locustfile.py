"""
Performance Load Tests - 100+ Agent Simulation

Locust load testing for ALS 2.0 Enterprise.
Simulates high-load scenarios with concurrent agents.

Usage:
    locust -f tests/performance/locustfile.py --host=http://localhost:8100  # Port updated from 8000 to 8100

Or headless:
    locust -f tests/performance/locustfile.py --headless -u 100 -r 10 --run-time 5m
"""

import random
import uuid
from datetime import datetime, timezone

from locust import HttpUser, between, events, task
from locust.runners import MasterRunner


class ALSAgentUser(HttpUser):
    """
    Simulates an ALS agent making requests.
    """

    wait_time = between(1, 5)  # Wait 1-5 seconds between tasks

    def on_start(self):
        """Initialize agent session."""
        self.agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        self.tenant_id = random.randint(1, 10)
        self.contracts = []

        # Register agent
        self.client.post(
            "/api/v1/als/agents/register",
            json={
                "agent_id": self.agent_id,
                "tenant_id": self.tenant_id,
                "capabilities": ["analysis", "execution"],
            },
        )

    @task(5)
    def create_contract(self):
        """Simulate creating an A2A contract."""
        contract_id = f"contract_{uuid.uuid4().hex[:8]}"

        response = self.client.post(
            "/api/v1/als/contracts",
            json={
                "contract_id": contract_id,
                "tenant_id": self.tenant_id,
                "producer_id": self.agent_id,
                "consumer_id": f"agent_{random.randint(1, 100)}",
                "schema_ref": "test.task@1.0.0",
                "prana_cost": random.randint(10, 100),
                "payload": {"task": "analysis", "data": "sample"},
            },
        )

        if response.status_code == 201:
            self.contracts.append(contract_id)

    @task(3)
    def execute_contract(self):
        """Simulate contract execution."""
        if not self.contracts:
            return

        contract_id = random.choice(self.contracts)

        self.client.post(
            f"/api/v1/als/contracts/{contract_id}/execute",
            json={
                "executor_id": self.agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @task(2)
    def query_health(self):
        """Simulate health check."""
        self.client.get(f"/api/v1/als/agents/{self.agent_id}/health")

    @task(1)
    def signal_emit(self):
        """Simulate signal emission."""
        self.client.post(
            "/api/v1/als/signals/emit",
            json={
                "tenant_id": self.tenant_id,
                "source_agent_id": self.agent_id,
                "tier": "COGNITIVE",
                "payload": {"type": "status_update", "status": "active"},
            },
        )

    def on_stop(self):
        """Cleanup agent session."""
        self.client.post(f"/api/v1/als/agents/{self.agent_id}/unregister")


class ALSChiefUser(HttpUser):
    """
    Simulates ChiefOrchestrator load.
    """

    wait_time = between(0.5, 2)

    @task(10)
    def delegate_task(self):
        """Simulate task delegation."""
        self.client.post(
            "/api/v1/als/tasks/delegate",
            json={
                "tenant_id": random.randint(1, 10),
                "task_type": random.choice(["analysis", "execution", "review"]),
                "payload": {"data": "test_payload"},
                "priority": random.randint(1, 5),
            },
        )

    @task(5)
    def get_system_health(self):
        """Simulate health check."""
        self.client.get("/api/v1/als/health")

    @task(2)
    def broadcast_message(self):
        """Simulate broadcast."""
        self.client.post(
            "/api/v1/als/broadcast",
            json={
                "tenant_id": random.randint(1, 10),
                "message": "system_notification",
                "payload": {"type": "announcement"},
            },
        )


class ALSAuditUser(HttpUser):
    """
    Simulates audit log queries.
    """

    wait_time = between(5, 15)

    @task(1)
    def query_audit_log(self):
        """Simulate audit log query."""
        self.client.get(
            "/api/v1/als/audit/events",
            params={
                "tenant_id": random.randint(1, 10),
                "since": "2026-01-01T00:00:00Z",
                "limit": 100,
            },
        )


# Custom event handlers
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
    """Log slow requests."""
    if response_time > 1000:  # > 1 second
        print(f"SLOW REQUEST: {name} took {response_time}ms")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Setup before test."""
    print(f"Starting load test with {environment.runner.target_user_count} users")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Cleanup after test."""
    print("Load test completed")

    # Print summary statistics
    if isinstance(environment.runner, MasterRunner):
        stats = environment.runner.stats
        print(f"\n{'='*60}")
        print("PERFORMANCE SUMMARY")
        print(f"{'='*60}")
        print(f"Total Requests: {stats.total.num_requests}")
        print(f"Failed Requests: {stats.total.num_failures}")
        print(f"Avg Response Time: {stats.total.avg_response_time:.2f}ms")
        print(f"95th Percentile: {stats.total.get_response_time_percentile(0.95):.2f}ms")
        print(f"RPS: {stats.total.total_rps:.2f}")
        print(f"{'='*60}")
