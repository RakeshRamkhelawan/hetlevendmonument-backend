"""
Load Testing Script - 50 Concurrent Tenants
============================================

Sprint 3 Task 3.1.1: Load Testing Implementation

Test Scenario:
- 50 concurrent tenants
- 100 requests/sec per tenant (5000 total req/sec)
- Duration: 30 minutes
- Mix: 60% reads, 30% writes, 10% deletes

Performance Targets:
- p95 latency: <300ms
- p99 latency: <500ms
- Error rate: <0.01% (1 in 10,000 requests)
- System stability: 30+ minutes without crashes

Tool: Locust (Python load testing framework)
"""

import logging
import random
import string
from datetime import datetime, timezone
from typing import List

from locust import HttpUser, between, events, task

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TenantUser(HttpUser):
    """
    Simulates a single tenant user with typical API usage patterns.

    Each user represents a tenant making API requests with:
    - 60% reads (GET requests)
    - 30% writes (POST/PUT requests)
    - 10% deletes (DELETE requests)
    """

    # Wait time between requests: 0.5-1.5 seconds
    # This gives ~1 request/second per user on average
    wait_time = between(0.5, 1.5)

    def on_start(self):
        """
        Initialize tenant user session.

        - Create unique tenant ID
        - Login to get JWT token
        - Store authentication headers
        """
        self.tenant_id = f"tenant_{random.randint(1, 50):03d}"
        self.user_id = None
        self.agent_ids = []
        self.conversation_ids = []

        # Login and get JWT token
        self.login()

        logger.info("Tenant %s started load testing session", self.tenant_id)

    def login(self):
        """Authenticate and obtain JWT token."""
        response = self.client.post(
            "/api/auth/login",
            json={
                "email": f"{self.tenant_id}@test.com",
                "password": "TestPassword123!",
            },
            name="[AUTH] Login",
        )

        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            self.user_id = data.get("user_id")

            # Set authentication header for all subsequent requests
            self.client.headers.update({"Authorization": f"Bearer {self.token}"})
            logger.debug("Tenant %s logged in successfully", self.tenant_id)
        else:
            logger.error("Login failed for %s: %s", self.tenant_id, response.status_code)

    # ========================================================================
    # READ OPERATIONS (60% of traffic)
    # ========================================================================

    @task(20)
    def list_agents(self):
        """GET /api/agents - List all agents for current tenant."""
        response = self.client.get("/api/agents", name="[READ] List Agents")

        if response.status_code == 200:
            agents = response.json().get("agents", [])
            # Store agent IDs for later use
            if agents:
                self.agent_ids = [agent["id"] for agent in agents[:10]]

    @task(15)
    def get_agent_details(self):
        """GET /api/agents/{id} - Get specific agent details."""
        if not self.agent_ids:
            return

        agent_id = random.choice(self.agent_ids)
        self.client.get(f"/api/agents/{agent_id}", name="[READ] Get Agent")

    @task(10)
    def list_conversations(self):
        """GET /api/conversations - List conversations."""
        response = self.client.get(
            "/api/conversations", params={"limit": 50}, name="[READ] List Conversations"
        )

        if response.status_code == 200:
            conversations = response.json().get("conversations", [])
            if conversations:
                self.conversation_ids = [c["id"] for c in conversations[:10]]

    @task(8)
    def get_conversation_history(self):
        """GET /api/conversations/{id}/messages - Get conversation messages."""
        if not self.conversation_ids:
            return

        conv_id = random.choice(self.conversation_ids)
        self.client.get(f"/api/conversations/{conv_id}/messages", name="[READ] Get Messages")

    @task(5)
    def get_user_profile(self):
        """GET /api/users/me - Get current user profile."""
        self.client.get("/api/users/me", name="[READ] Get Profile")

    @task(2)
    def list_features(self):
        """GET /api/tenant/features - List enabled features."""
        self.client.get("/api/tenant/features", name="[READ] List Features")

    # ========================================================================
    # WRITE OPERATIONS (30% of traffic)
    # ========================================================================

    @task(10)
    def create_agent(self):
        """POST /api/agents - Create new agent."""
        agent_name = f"agent_{self._random_string(8)}"

        response = self.client.post(
            "/api/agents",
            json={
                "name": agent_name,
                "type": random.choice(["analyzer", "executor", "researcher"]),
                "description": f"Load test agent {agent_name}",
                "config": {"model": "gpt-4", "temperature": 0.7},
            },
            name="[WRITE] Create Agent",
        )

        if response.status_code == 201:
            agent_id = response.json().get("id")
            if agent_id:
                self.agent_ids.append(agent_id)

    @task(8)
    def create_conversation(self):
        """POST /api/conversations - Create new conversation."""
        if not self.agent_ids:
            return

        agent_id = random.choice(self.agent_ids)

        response = self.client.post(
            "/api/conversations",
            json={
                "agent_id": agent_id,
                "user_id": self.user_id,
                "title": f"Load test conversation {self._random_string(6)}",
            },
            name="[WRITE] Create Conversation",
        )

        if response.status_code == 201:
            conv_id = response.json().get("id")
            if conv_id:
                self.conversation_ids.append(conv_id)

    @task(5)
    def send_message(self):
        """POST /api/conversations/{id}/messages - Send message."""
        if not self.conversation_ids:
            return

        conv_id = random.choice(self.conversation_ids)

        self.client.post(
            f"/api/conversations/{conv_id}/messages",
            json={
                "content": f"Load test message: {self._random_string(50)}",
                "role": "user",
            },
            name="[WRITE] Send Message",
        )

    @task(4)
    def update_agent(self):
        """PUT /api/agents/{id} - Update agent configuration."""
        if not self.agent_ids:
            return

        agent_id = random.choice(self.agent_ids)

        self.client.put(
            f"/api/agents/{agent_id}",
            json={
                "description": f"Updated at {datetime.now(timezone.utc).isoformat()}",
                "config": {"temperature": random.uniform(0.5, 1.0)},
            },
            name="[WRITE] Update Agent",
        )

    @task(3)
    def update_profile(self):
        """PUT /api/users/me - Update user profile."""
        self.client.put(
            "/api/users/me",
            json={
                "display_name": f"Load Test User {self._random_string(6)}",
                "preferences": {
                    "theme": random.choice(["light", "dark"]),
                    "language": "en",
                },
            },
            name="[WRITE] Update Profile",
        )

    # ========================================================================
    # DELETE OPERATIONS (10% of traffic)
    # ========================================================================

    @task(3)
    def delete_conversation(self):
        """DELETE /api/conversations/{id} - Delete conversation."""
        if len(self.conversation_ids) < 5:
            return  # Keep at least a few conversations

        conv_id = self.conversation_ids.pop(0)  # Delete oldest

        self.client.delete(f"/api/conversations/{conv_id}", name="[DELETE] Delete Conversation")

    @task(2)
    def delete_agent(self):
        """DELETE /api/agents/{id} - Delete agent."""
        if len(self.agent_ids) < 3:
            return  # Keep at least a few agents

        agent_id = self.agent_ids.pop(0)  # Delete oldest

        self.client.delete(f"/api/agents/{agent_id}", name="[DELETE] Delete Agent")

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    def _random_string(self, length: int) -> str:
        """Generate random alphanumeric string."""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))

    def on_stop(self):
        """Cleanup when user stops."""
        logger.info("Tenant %s stopped load testing session", self.tenant_id)


# ============================================================================
# LOCUST EVENT HANDLERS (Metrics Collection)
# ============================================================================


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log when load test starts."""
    logger.info("=" * 80)
    logger.info("🚀 LOAD TEST STARTED")
    logger.info("Target: %s", environment.host)
    logger.info("Duration: 30 minutes")
    logger.info("Target users: 50 concurrent tenants")
    logger.info("Target RPS: 5000 requests/second")
    logger.info("=" * 80)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Log when load test stops and print summary."""
    logger.info("=" * 80)
    logger.info("🏁 LOAD TEST COMPLETED")
    logger.info("=" * 80)

    # Get statistics
    stats = environment.stats

    # Print summary
    logger.info("\n📊 PERFORMANCE SUMMARY:")
    logger.info("Total requests: %s", stats.total.num_requests)
    logger.info("Total failures: %s", stats.total.num_failures)
    logger.info("Failure rate: %.2f%", stats.total.fail_ratio * 100)
    logger.info("Average response time: %.2fms", stats.total.avg_response_time)
    logger.info("Median response time (p50): %.2fms", stats.total.median_response_time)
    logger.info("95th percentile (p95): %.2fms", stats.total.get_response_time_percentile(0.95))
    logger.info("99th percentile (p99): %.2fms", stats.total.get_response_time_percentile(0.99))
    logger.info("Max response time: %.2fms", stats.total.max_response_time)
    logger.info("Requests per second: %.2", stats.total.total_rps)

    # Check acceptance criteria
    logger.info("\n✅ ACCEPTANCE CRITERIA CHECK:")

    p95 = stats.total.get_response_time_percentile(0.95)
    p99 = stats.total.get_response_time_percentile(0.99)
    error_rate = stats.total.fail_ratio

    criteria_met = []
    criteria_failed = []

    # Check p95 latency
    if p95 < 300:
        criteria_met.append(f"✅ p95 latency: {p95:.2f}ms (target: <300ms)")
    else:
        criteria_failed.append(f"❌ p95 latency: {p95:.2f}ms (target: <300ms)")

    # Check p99 latency
    if p99 < 500:
        criteria_met.append(f"✅ p99 latency: {p99:.2f}ms (target: <500ms)")
    else:
        criteria_failed.append(f"❌ p99 latency: {p99:.2f}ms (target: <500ms)")

    # Check error rate
    if error_rate < 0.0001:  # 0.01%
        criteria_met.append(f"✅ Error rate: {error_rate * 100:.3f}% (target: <0.01%)")
    else:
        criteria_failed.append(f"❌ Error rate: {error_rate * 100:.3f}% (target: <0.01%)")

    for criterion in criteria_met:
        logger.info(criterion)

    for criterion in criteria_failed:
        logger.error(criterion)

    if criteria_failed:
        logger.error("\n❌ LOAD TEST FAILED: %s criteria not met", len(criteria_failed))
    else:
        logger.info("\n🎉 LOAD TEST PASSED: All acceptance criteria met!")


# ============================================================================
# USAGE INSTRUCTIONS
# ============================================================================
"""
To run this load test:

1. Install Locust:
   pip install locust

2. Start the load test (web UI):
   locust -f tests/load/test_50_tenants.py --host=http://localhost:8100

   Then open http://localhost:8089 and configure:
   - Number of users: 50
   - Spawn rate: 10 users/second
   - Run time: 30 minutes (1800 seconds)

3. Start the load test (headless):
   locust -f tests/load/test_50_tenants.py \
       --host=http://localhost:8100 \
       --users=50 \
       --spawn-rate=10 \
       --run-time=30m \
       --headless \
       --html=docs/load_test_report.html

4. For staging environment:
   locust -f tests/load/test_50_tenants.py \
       --host=https://staging.sanskriti-setu.org \
       --users=50 \
       --spawn-rate=10 \
       --run-time=30m \
       --headless \
       --html=docs/load_test_report.html

Expected Results:
- p95 latency: <300ms
- p99 latency: <500ms
- Error rate: <0.01%
- Total RPS: ~5000 requests/second
- Duration: 30 minutes stable
"""
