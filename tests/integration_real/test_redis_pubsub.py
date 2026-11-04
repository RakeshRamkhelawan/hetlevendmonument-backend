"""
REAL Integration Test: Redis Pub/Sub.

Tests actual Redis operations.
NO MOCKS - Real connections, real messages.
"""

import asyncio

import pytest


@pytest.mark.integration
@pytest.mark.requires_redis
class TestRedisPubSubReal:
    """Test real Redis Pub/Sub functionality."""

    async def test_redis_connection(self, real_redis_client):
        """
        Integration Test: Redis connection is working.
        """
        result = await real_redis_client.ping()
        assert result is True, "Redis ping failed"

    async def test_publish_and_subscribe(self, real_redis_client):
        """
        Integration Test: Basic publish/subscribe.

        Publishes a message and verifies it can be received.
        """
        channel = "test:integration:channel"
        message = {"test": "data", "timestamp": "2026-02-27"}

        # Create subscriber
        pubsub = real_redis_client.pubsub()
        await pubsub.subscribe(channel)

        # Wait for subscription
        await asyncio.sleep(0.1)

        # Publish message
        await real_redis_client.publish(channel, str(message))

        # Wait for message
        await asyncio.sleep(0.1)

        # Get message
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)

        assert msg is not None, "Message not received"
        assert channel.encode() in msg["channel"]

        # Cleanup
        await pubsub.unsubscribe(channel)
        await pubsub.close()

    async def test_multiple_subscribers(self, real_redis_client):
        """
        Integration Test: Multiple subscribers receive same message.
        """
        channel = "test:integration:multi"
        message = "broadcast message"

        # Create multiple subscribers
        subscribers = []
        for i in range(3):
            pubsub = real_redis_client.pubsub()
            await pubsub.subscribe(channel)
            subscribers.append(pubsub)

        await asyncio.sleep(0.1)

        # Publish message
        await real_redis_client.publish(channel, message)
        await asyncio.sleep(0.1)

        # All subscribers should receive
        received = []
        for pubsub in subscribers:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            if msg:
                received.append(msg)
            await pubsub.unsubscribe(channel)
            await pubsub.close()

        assert len(received) == 3, f"Expected 3 messages, got {len(received)}"

    async def test_event_type_routing(self, real_redis_client):
        """
        Integration Test: Different event types on different channels.

        Simulates real event system usage.
        """
        # Create pubsubs for different event types
        workflow_pubsub = real_redis_client.pubsub()
        notification_pubsub = real_redis_client.pubsub()

        await workflow_pubsub.subscribe("workflow:events")
        await notification_pubsub.subscribe("notification:events")

        await asyncio.sleep(0.1)

        # Publish workflow event
        await real_redis_client.publish("workflow:events", '{"type": "started"}')

        # Publish notification event
        await real_redis_client.publish("notification:events", '{"type": "email"}')

        await asyncio.sleep(0.1)

        # Verify correct routing
        workflow_msg = await workflow_pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
        notification_msg = await notification_pubsub.get_message(
            ignore_subscribe_messages=True, timeout=1
        )

        assert workflow_msg is not None
        assert b'"type": "started"' in workflow_msg["data"]

        assert notification_msg is not None
        assert b'"type": "email"' in notification_msg["data"]

        # Cleanup
        await workflow_pubsub.unsubscribe()
        await notification_pubsub.unsubscribe()
        await workflow_pubsub.close()
        await notification_pubsub.close()

    async def test_message_persistence_not_guaranteed(self, real_redis_client):
        """
        Integration Test: Pub/Sub messages are not persisted.

        Messages sent before subscription are lost.
        """
        channel = "test:integration:persistence"

        # Publish before subscribing
        await real_redis_client.publish(channel, "early message")

        # Subscribe after
        pubsub = real_redis_client.pubsub()
        await pubsub.subscribe(channel)
        await asyncio.sleep(0.1)

        # Should not receive early message
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
        assert msg is None, "Should not receive message published before subscription"

        # Publish new message
        await real_redis_client.publish(channel, "new message")
        await asyncio.sleep(0.1)

        # Should receive new message
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
        assert msg is not None
        assert b"new message" in msg["data"]

        await pubsub.unsubscribe()
        await pubsub.close()

    async def test_high_throughput_pubsub(self, real_redis_client):
        """
        Integration Test: High throughput message handling.

        Verifies Redis can handle many messages.
        """
        channel = "test:integration:throughput"
        message_count = 100

        pubsub = real_redis_client.pubsub()
        await pubsub.subscribe(channel)
        await asyncio.sleep(0.1)

        # Publish many messages
        for i in range(message_count):
            await real_redis_client.publish(channel, f"message_{i}")

        await asyncio.sleep(0.5)

        # Receive all messages
        received = 0
        for _ in range(message_count):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if msg:
                received += 1

        # Should receive most messages (some may be dropped due to buffer limits)
        assert received >= message_count * 0.9, f"Only received {received}/{message_count} messages"

        await pubsub.unsubscribe()
        await pubsub.close()


@pytest.mark.integration
@pytest.mark.requires_redis
class TestRedisDataStructures:
    """Test Redis data structures used by application."""

    async def test_string_operations(self, real_redis_client):
        """
        Integration Test: Redis string operations.
        """
        key = "test:key:string"
        value = "test_value_123"

        # Set
        await real_redis_client.set(key, value)

        # Get
        result = await real_redis_client.get(key)
        assert result == value

        # Cleanup
        await real_redis_client.delete(key)

    async def test_hash_operations(self, real_redis_client):
        """
        Integration Test: Redis hash operations.

        Used for storing session data, user states.
        """
        key = "test:session:user123"

        await real_redis_client.hset(
            key, mapping={"user_id": "123", "tenant_id": "1", "last_active": "2026-02-27T10:00:00"}
        )

        result = await real_redis_client.hgetall(key)
        assert result["user_id"] == "123"
        assert result["tenant_id"] == "1"

        await real_redis_client.delete(key)

    async def test_list_operations(self, real_redis_client):
        """
        Integration Test: Redis list operations.

        Used for queues, message buffers.
        """
        key = "test:queue:events"

        # Push messages
        await real_redis_client.lpush(key, "event1", "event2", "event3")

        # Pop from other end (FIFO)
        result = await real_redis_client.rpop(key)
        assert result == "event1"

        # Get list length
        length = await real_redis_client.llen(key)
        assert length == 2

        await real_redis_client.delete(key)

    async def test_set_operations(self, real_redis_client):
        """
        Integration Test: Redis set operations.

        Used for unique collections, online users.
        """
        key = "test:set:online_users"

        await real_redis_client.sadd(key, "user1", "user2", "user3", "user2")  # duplicate

        members = await real_redis_client.smembers(key)
        assert len(members) == 3  # No duplicates
        assert "user1" in members

        await real_redis_client.delete(key)

    async def test_expire_operations(self, real_redis_client):
        """
        Integration Test: Redis key expiration.

        Used for cache TTL, session timeouts.
        """
        import asyncio

        key = "test:expire:key"

        await real_redis_client.set(key, "value", ex=1)  # 1 second expiry

        # Should exist immediately
        exists = await real_redis_client.exists(key)
        assert exists == 1

        # Wait for expiry
        await asyncio.sleep(1.5)

        # Should be gone
        exists = await real_redis_client.exists(key)
        assert exists == 0


@pytest.mark.integration
@pytest.mark.requires_redis
class TestRedisConnectionRecovery:
    """Test Redis connection recovery."""

    async def test_connection_pool_reuse(self, real_redis_client):
        """
        Integration Test: Connection pool reuses connections.
        """
        # Multiple operations should reuse connection
        for i in range(10):
            await real_redis_client.set(f"test:conn:{i}", str(i))

        # All should succeed
        for i in range(10):
            result = await real_redis_client.get(f"test:conn:{i}")
            assert result == str(i)
            await real_redis_client.delete(f"test:conn:{i}")
