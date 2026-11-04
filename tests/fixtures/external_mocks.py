"""
tests/fixtures/external_mocks.py - External Service Mocks

Mocks for external dependencies: Redis, MLflow en in-memory message queue.
All mocks use in-memory storage and are fully isolated.

KEY PRINCIPLES:
1. In-memory storage (no external connections)
2. Thread-safe operations
3. API-compatible with real services
4. Deterministic behavior

Created: 2025-12-11
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

import pytest

# ============================================================================
# FAKE REDIS CLIENT
# ============================================================================


class FakeRedisClient:
    """
    In-memory Redis mock with common operations.

    Supports: get, set, delete, exists, expire, incr, hset, hget, etc.
    No network calls - all data stored in memory.

    Example:
        >>> redis = FakeRedisClient()
        >>> await redis.set("key1", "value1", ex=60)
        >>> value = await redis.get("key1")
        >>> assert value == "value1"
    """

    def __init__(self):
        """Initialize empty in-memory store."""
        self._cache: Dict[str, str] = {}
        self._hashes: Dict[str, Dict[str, str]] = {}  # For HSET/HGET
        self._sets: Dict[str, Set[str]] = {}  # For SADD/SMEMBERS
        self._ttls: Dict[str, datetime] = {}  # Expiration times
        self.call_log: List[Dict[str, Any]] = []

    async def get(self, key: str) -> Optional[str]:
        """
        Get value by key.

        Returns:
            Value as string, or None if key doesn't exist or expired
        """
        self.call_log.append({"method": "get", "key": key})
        self._cleanup_expired()

        return self._cache.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        Set key to value with optional TTL.

        Args:
            key: Key name
            value: Value to store
            ex: Expiration in seconds
            px: Expiration in milliseconds
            nx: Only set if key does NOT exist
            xx: Only set if key DOES exist

        Returns:
            True if set, False if conditions not met
        """
        self.call_log.append({"method": "set", "key": key, "value": value, "ex": ex})
        self._cleanup_expired()

        # Check nx/xx conditions
        exists = key in self._cache
        if nx and exists:
            return False
        if xx and not exists:
            return False

        self._cache[key] = value

        # Set TTL
        if ex:
            self._ttls[key] = datetime.now(timezone.utc) + timedelta(seconds=ex)
        elif px:
            self._ttls[key] = datetime.now(timezone.utc) + timedelta(milliseconds=px)

        return True

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        """Set key to value with expiration in seconds."""
        self.call_log.append(
            {"method": "setex", "key": key, "seconds": seconds, "value": value}
        )
        self._cleanup_expired()
        self._cache[key] = value
        self._ttls[key] = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        return True

    async def delete(self, *keys: str) -> int:
        """
        Delete one or more keys.

        Returns:
            Number of keys deleted
        """
        self.call_log.append({"method": "delete", "keys": keys})

        deleted = 0
        for key in keys:
            if key in self._cache:
                del self._cache[key]
                self._ttls.pop(key, None)
                deleted += 1

        return deleted

    async def exists(self, *keys: str) -> int:
        """
        Check how many keys exist.

        Returns:
            Count of existing keys
        """
        self._cleanup_expired()
        return sum(1 for key in keys if key in self._cache)

    async def expire(self, key: str, seconds: int) -> bool:
        """
        Set TTL on existing key.

        Returns:
            True if TTL was set, False if key doesn't exist
        """
        if key in self._cache:
            self._ttls[key] = datetime.now(timezone.utc) + timedelta(seconds=seconds)
            return True
        return False

    async def incr(self, key: str) -> int:
        """
        Increment integer value.

        Returns:
            New value after increment
        """
        current = int(self._cache.get(key, 0))
        new_value = current + 1
        self._cache[key] = str(new_value)
        return new_value

    async def decr(self, key: str) -> int:
        """Decrement integer value."""
        current = int(self._cache.get(key, 0))
        new_value = current - 1
        self._cache[key] = str(new_value)
        return new_value

    # Hash operations (HSET, HGET, etc.)
    async def hset(self, name: str, key: str, value: str) -> int:
        """Set hash field."""
        if name not in self._hashes:
            self._hashes[name] = {}

        existed = key in self._hashes[name]
        self._hashes[name][key] = value
        return 0 if existed else 1

    async def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field."""
        return self._hashes.get(name, {}).get(key)

    async def hgetall(self, name: str) -> Dict[str, str]:
        """Get all hash fields."""
        return self._hashes.get(name, {}).copy()

    # Set operations (SADD, SMEMBERS, etc.)
    async def sadd(self, key: str, *members: str) -> int:
        """Add members to set."""
        if key not in self._sets:
            self._sets[key] = set()

        before_size = len(self._sets[key])
        self._sets[key].update(members)
        return len(self._sets[key]) - before_size

    async def smembers(self, key: str) -> Set[str]:
        """Get all set members."""
        return self._sets.get(key, set()).copy()

    async def sismember(self, key: str, member: str) -> bool:
        """Check if member is in set."""
        return member in self._sets.get(key, set())

    # Utility methods
    async def flushdb(self):
        """Clear all data."""
        self._cache.clear()
        self._hashes.clear()
        self._sets.clear()
        self._ttls.clear()

    async def close(self):
        """Close connection (no-op for mock)."""
        pass

    def _cleanup_expired(self):
        """Remove expired keys."""
        now = datetime.now(timezone.utc)
        expired_keys = [key for key, expiry in self._ttls.items() if expiry <= now]

        for key in expired_keys:
            self._cache.pop(key, None)
            self._ttls.pop(key, None)


class FakeRabbitMQ:  # NOTE: deprecated — RabbitMQ verwijderd (ADR-006). Klasse behouden voor backward-compat imports.
    """
    In-memory message queue mock (voorheen RabbitMQ, nu alleen nog voor backward-compatibiliteit).

    Supports: publish, consume, declare_queue, bind_queue, purge_queue.

    Example:
        >>> mq = FakeRabbitMQ()
        >>> await mq.declare_queue("tasks")
        >>> await mq.publish("tasks", {"job": "process_data"})
        >>> message = await mq.consume("tasks")
        >>> assert message["job"] == "process_data"
    """

    def __init__(self):
        """Initialize empty message broker."""
        self._queues: Dict[str, List[Dict[str, Any]]] = {}
        self._exchanges: Dict[str, Set[str]] = {}  # exchange -> bound queues
        self.call_log: List[Dict[str, Any]] = []

    async def declare_queue(
        self,
        queue: str,
        durable: bool = False,
        auto_delete: bool = False,
    ) -> bool:
        """
        Declare a queue.

        Args:
            queue: Queue name
            durable: Persist across restarts (ignored in mock)
            auto_delete: Delete when no consumers (ignored in mock)

        Returns:
            True if queue was created
        """
        self.call_log.append({"method": "declare_queue", "queue": queue})

        if queue not in self._queues:
            self._queues[queue] = []
            return True

        return False

    async def publish(
        self,
        queue: str,
        message: Dict[str, Any],
        exchange: str = "",
        routing_key: str = "",
    ) -> bool:
        """
        Publish message to queue.

        Args:
            queue: Target queue name
            message: Message body (dict)
            exchange: Exchange name (ignored in simple mock)
            routing_key: Routing key (ignored in simple mock)

        Returns:
            True if published
        """
        self.call_log.append(
            {
                "method": "publish",
                "queue": queue,
                "message": message,
            }
        )

        # Auto-create queue if not exists
        if queue not in self._queues:
            self._queues[queue] = []

        # Add message to queue (FIFO)
        self._queues[queue].append(
            {
                "body": message,
                "timestamp": datetime.now(timezone.utc),
            }
        )

        return True

    async def consume(
        self,
        queue: str,
        auto_ack: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Consume message from queue (FIFO).

        Args:
            queue: Queue name
            auto_ack: Auto-acknowledge (ignored in mock)

        Returns:
            Message body dict, or None if queue empty
        """
        self.call_log.append({"method": "consume", "queue": queue})

        if queue in self._queues and self._queues[queue]:
            message_envelope = self._queues[queue].pop(0)
            return message_envelope["body"]

        return None

    async def bind_queue(
        self,
        queue: str,
        exchange: str,
        routing_key: str = "",
    ) -> bool:
        """
        Bind queue to exchange.

        Args:
            queue: Queue name
            exchange: Exchange name
            routing_key: Routing key pattern

        Returns:
            True if bound
        """
        if exchange not in self._exchanges:
            self._exchanges[exchange] = set()

        self._exchanges[exchange].add(queue)
        return True

    async def purge_queue(self, queue: str) -> int:
        """
        Remove all messages from queue.

        Returns:
            Number of messages purged
        """
        if queue in self._queues:
            count = len(self._queues[queue])
            self._queues[queue] = []
            return count

        return 0

    def get_queue_size(self, queue: str) -> int:
        """Get number of messages in queue."""
        return len(self._queues.get(queue, []))

    def reset(self):
        """Clear all queues and logs."""
        self._queues.clear()
        self._exchanges.clear()
        self.call_log.clear()


# ============================================================================
# MOCK MLFLOW CLIENT
# ============================================================================


@dataclass
class MLflowRun:
    """MLflow run metadata."""

    run_id: str
    experiment_id: str
    status: str = "RUNNING"
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    params: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)


class MockMLflowClient:
    """
    Mock MLflow tracking client.

    Supports: create_experiment, start_run, log_param, log_metric, end_run.
    All data stored in memory.

    Example:
        >>> mlflow = MockMLflowClient()
        >>> exp_id = mlflow.create_experiment("test_exp")
        >>> run = mlflow.create_run(exp_id)
        >>> mlflow.log_param(run.info.run_id, "lr", 0.01)
        >>> mlflow.log_metric(run.info.run_id, "accuracy", 0.95)
    """

    def __init__(self):
        """Initialize empty tracking store."""
        self.experiments: Dict[str, Dict[str, Any]] = {}
        self.runs: Dict[str, MLflowRun] = {}
        self.call_log: List[Dict[str, Any]] = []
        self._next_exp_id = 1
        self._next_run_id = 1

    def create_experiment(self, name: str) -> str:
        """
        Create experiment.

        Args:
            name: Experiment name

        Returns:
            Experiment ID (string)
        """
        exp_id = str(self._next_exp_id)
        self._next_exp_id += 1

        self.experiments[exp_id] = {
            "experiment_id": exp_id,
            "name": name,
            "artifact_location": f"/tmp/mlflow/{exp_id}",
            "lifecycle_stage": "active",
        }

        self.call_log.append({"method": "create_experiment", "name": name})
        return exp_id

    def create_run(self, experiment_id: str, tags: Optional[Dict[str, str]] = None):
        """
        Create a new run.

        Returns:
            Mock Run object with run_id in info attribute
        """
        run_id = f"run_{self._next_run_id}"
        self._next_run_id += 1

        run = MLflowRun(
            run_id=run_id,
            experiment_id=experiment_id,
            tags=tags or {},
        )

        self.runs[run_id] = run
        self.call_log.append({"method": "create_run", "run_id": run_id})

        # Return mock Run object
        from unittest.mock import MagicMock

        mock_run = MagicMock()
        mock_run.info.run_id = run_id
        mock_run.info.experiment_id = experiment_id
        mock_run.info.status = "RUNNING"

        return mock_run

    def log_param(self, run_id: str, key: str, value: Any):
        """Log parameter."""
        if run_id in self.runs:
            self.runs[run_id].params[key] = value
            self.call_log.append({"method": "log_param", "run_id": run_id, "key": key})

    def log_metric(self, run_id: str, key: str, value: float, step: int = 0):
        """Log metric."""
        if run_id in self.runs:
            self.runs[run_id].metrics[key] = value
            self.call_log.append({"method": "log_metric", "run_id": run_id, "key": key})

    def set_tag(self, run_id: str, key: str, value: str):
        """Set tag."""
        if run_id in self.runs:
            self.runs[run_id].tags[key] = value

    def log_artifact(self, run_id: str, local_path: str):
        """Log artifact (no-op in mock)."""
        self.call_log.append({"method": "log_artifact", "run_id": run_id})

    def end_run(self, run_id: str, status: str = "FINISHED"):
        """End run."""
        if run_id in self.runs:
            self.runs[run_id].status = status
            self.runs[run_id].end_time = datetime.now(timezone.utc)

    def get_run(self, run_id: str) -> Optional[MLflowRun]:
        """Get run by ID."""
        return self.runs.get(run_id)

    def search_runs(self, experiment_ids: List[str]) -> List[MLflowRun]:
        """Search runs by experiment."""
        return [run for run in self.runs.values() if run.experiment_id in experiment_ids]

    def reset(self):
        """Clear all data."""
        self.experiments.clear()
        self.runs.clear()
        self.call_log.clear()


# ============================================================================
# MOCK STRIPE SERVICE
# ============================================================================


class MockStripeCustomer:
    """Mock Stripe Customer object."""

    def __init__(self, customer_id: str, email: str, name: Optional[str] = None):
        self.id = customer_id
        self.email = email
        self.name = name or email
        self.metadata: Dict[str, Any] = {}


class MockStripeSession:
    """Mock Stripe Checkout Session object."""

    def __init__(
        self,
        session_id: str,
        customer_id: str,
        url: str,
        status: str = "open",
        payment_status: str = "unpaid",
    ):
        self.id = session_id
        self.customer = customer_id
        self.url = url
        self.status = status
        self.payment_status = payment_status


class MockStripeService:
    """
    Mock Stripe service for testing payments without real API calls.

    Supports: create_customer, create_checkout_session, retrieve_session
    All data stored in memory.

    Example:
        >>> stripe = MockStripeService()
        >>> customer_id = await stripe.create_customer("test@example.com")
        >>> session_url = await stripe.create_checkout_session(
        ...     customer_id=customer_id,
        ...     success_url="https://example.com/success",
        ...     cancel_url="https://example.com/cancel",
        ...     price_id="price_123"
        ... )
    """

    def __init__(self, api_key: str = "mock_stripe_key"):
        """Initialize mock Stripe service with in-memory storage."""
        self.api_key = api_key
        self._customers: Dict[str, MockStripeCustomer] = {}
        self._sessions: Dict[str, MockStripeSession] = {}
        self._customer_counter = 0
        self._session_counter = 0
        self.call_log: List[Dict[str, Any]] = []
        self.should_fail = False
        self.failure_message = "Stripe API error (mock)"

    async def create_customer(
        self,
        email: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Create a mock customer.

        Returns:
            Customer ID (cus_mock_XXX) or None if should_fail=True
        """
        self.call_log.append(
            {
                "method": "create_customer",
                "email": email,
                "name": name,
                "metadata": metadata,
            }
        )

        if self.should_fail:
            return None

        self._customer_counter += 1
        customer_id = f"cus_mock_{self._customer_counter:06d}"
        customer = MockStripeCustomer(customer_id=customer_id, email=email, name=name)
        if metadata:
            customer.metadata = metadata

        self._customers[customer_id] = customer
        return customer_id

    async def create_checkout_session(
        self,
        customer_id: str,
        success_url: str,
        cancel_url: str,
        price_id: str,
        mode: str = "subscription",
    ) -> Optional[str]:
        """
        Create a mock checkout session.

        Returns:
            Checkout session URL or None if should_fail=True
        """
        self.call_log.append(
            {
                "method": "create_checkout_session",
                "customer_id": customer_id,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "price_id": price_id,
                "mode": mode,
            }
        )

        if self.should_fail:
            return None

        self._session_counter += 1
        session_id = f"cs_mock_{self._session_counter:06d}"
        session_url = f"https://checkout.stripe.com/mock/session/{session_id}"

        session = MockStripeSession(
            session_id=session_id,
            customer_id=customer_id,
            url=session_url,
        )

        self._sessions[session_id] = session
        return session_url

    async def retrieve_session(self, session_id: str) -> Optional[MockStripeSession]:
        """Retrieve a mock session by ID."""
        return self._sessions.get(session_id)

    async def retrieve_customer(self, customer_id: str) -> Optional[MockStripeCustomer]:
        """Retrieve a mock customer by ID."""
        return self._customers.get(customer_id)

    def set_fail_mode(self, should_fail: bool, message: str = "Stripe API error (mock)"):
        """Enable/disable failure mode."""
        self.should_fail = should_fail
        self.failure_message = message

    def reset(self):
        """Clear all mock data."""
        self._customers.clear()
        self._sessions.clear()
        self.call_log.clear()
        self._customer_counter = 0
        self._session_counter = 0
        self.should_fail = False


# ============================================================================
# MOCK EMAIL SERVICE
# ============================================================================


class MockEmailMessage:
    """Mock email message for testing."""

    def __init__(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_email: Optional[str] = None,
    ):
        self.to = to
        self.subject = subject
        self.body = body
        self.html_body = html_body
        self.from_email = from_email or "test@example.com"
        self.sent_at: Optional[datetime] = None


class MockEmailService:
    """
    Mock email service for testing without real SMTP/API calls.

    Captures all sent emails in memory for verification.

    Example:
        >>> email_service = MockEmailService()
        >>> await email_service.send("user@example.com", "Welcome", "Hello!")
        >>> assert len(email_service.sent_emails) == 1
        >>> assert email_service.sent_emails[0].subject == "Welcome"
    """

    def __init__(self):
        """Initialize mock email service."""
        self.sent_emails: List[MockEmailMessage] = []
        self.call_log: List[Dict[str, Any]] = []
        self.should_fail = False
        self.failure_message = "Email service error (mock)"

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> bool:
        """
        Mock send email.

        Returns:
            True if email captured, False if should_fail=True
        """
        self.call_log.append(
            {
                "method": "send",
                "to": to,
                "subject": subject,
                "body": body,
            }
        )

        if self.should_fail:
            return False

        message = MockEmailMessage(
            to=to,
            subject=subject,
            body=body,
            html_body=html_body,
            from_email=from_email,
        )
        message.sent_at = datetime.now(timezone.utc)
        self.sent_emails.append(message)
        return True

    async def send_template(
        self,
        to: str,
        template_name: str,
        context: Dict[str, Any],
        from_email: Optional[str] = None,
    ) -> bool:
        """Mock send template email."""
        self.call_log.append(
            {
                "method": "send_template",
                "to": to,
                "template_name": template_name,
                "context": context,
            }
        )

        if self.should_fail:
            return False

        body = f"Template: {template_name} with context: {context}"
        message = MockEmailMessage(
            to=to,
            subject=f"Template: {template_name}",
            body=body,
            from_email=from_email,
        )
        message.sent_at = datetime.now(timezone.utc)
        self.sent_emails.append(message)
        return True

    def get_sent_emails(self, to: Optional[str] = None) -> List[MockEmailMessage]:
        """
        Get sent emails, optionally filtered by recipient.

        Args:
            to: Filter by recipient email address

        Returns:
            List of sent email messages
        """
        if to:
            return [e for e in self.sent_emails if e.to == to]
        return self.sent_emails.copy()

    def clear_sent_emails(self):
        """Clear all sent emails."""
        self.sent_emails.clear()

    def set_fail_mode(self, should_fail: bool, message: str = "Email service error (mock)"):
        """Enable/disable failure mode."""
        self.should_fail = should_fail
        self.failure_message = message

    def reset(self):
        """Reset mock state."""
        self.sent_emails.clear()
        self.call_log.clear()
        self.should_fail = False


# ============================================================================
# PYTEST FIXTURES
# ============================================================================


@pytest.fixture
def mock_stripe_service() -> MockStripeService:
    """
    Provide MockStripeService for testing.

    Usage:
        async def test_checkout(mock_stripe_service):
            customer_id = await mock_stripe_service.create_customer("test@example.com")
            session_url = await mock_stripe_service.create_checkout_session(
                customer_id=customer_id,
                success_url="https://example.com/success",
                cancel_url="https://example.com/cancel",
                price_id="price_123"
            )
            assert session_url is not None
            assert "stripe.com" in session_url
    """
    return MockStripeService()


@pytest.fixture
def mock_email_service() -> MockEmailService:
    """
    Provide MockEmailService for testing.

    Usage:
        async def test_welcome_email(mock_email_service):
            await mock_email_service.send("user@example.com", "Welcome", "Hello!")
            assert len(mock_email_service.sent_emails) == 1
            assert mock_email_service.sent_emails[0].subject == "Welcome"
    """
    return MockEmailService()


@pytest.fixture
def fake_redis_client() -> FakeRedisClient:
    """
    Provide FakeRedisClient for testing.

    Usage:
        async def test_cache(fake_redis_client):
            await fake_redis_client.set("key", "value")
            value = await fake_redis_client.get("key")
            assert value == "value"
    """
    return FakeRedisClient()


@pytest.fixture
def fake_rabbitmq() -> FakeRabbitMQ:
    """
    Provide FakeRabbitMQ for testing.

    Usage:
        async def test_queue(fake_rabbitmq):
            await fake_rabbitmq.declare_queue("tasks")
            await fake_rabbitmq.publish("tasks", {"job": "test"})
            message = await fake_rabbitmq.consume("tasks")
            assert message["job"] == "test"
    """
    return FakeRabbitMQ()


@pytest.fixture
def mock_mlflow_client() -> MockMLflowClient:
    """
    Provide MockMLflowClient for testing.

    Usage:
        def test_tracking(mock_mlflow_client):
            exp_id = mock_mlflow_client.create_experiment("test")
            run = mock_mlflow_client.create_run(exp_id)
            mock_mlflow_client.log_metric(run.info.run_id, "acc", 0.9)
    """
    return MockMLflowClient()
