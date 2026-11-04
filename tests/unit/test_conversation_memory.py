import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.agents.ultimate_cva.memory import ConversationMemory


@pytest.mark.asyncio
class TestConversationMemory:
    """Tests for Redis-backed ConversationMemory"""

    async def test_add_message(self, redis_client):
        """Test adding a message to history"""
        memory = ConversationMemory(redis_client, tenant_id=1)
        user_id = 123
        message = {"role": "user", "content": "Hello"}

        await memory.add_message(user_id, message)

        # Verify it's in Redis
        key = f"assistant:history:1:{user_id}"
        history_json = await redis_client.lrange(key, 0, -1)
        assert len(history_json) == 1
        assert json.loads(history_json[0]) == message

    async def test_get_history(self, redis_client):
        """Test retrieving message history"""
        memory = ConversationMemory(redis_client, tenant_id=1)
        user_id = 123
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        for msg in messages:
            await memory.add_message(user_id, msg)

        history = await memory.get_history(user_id)
        assert len(history) == 2
        assert history == messages

    async def test_clear_history(self, redis_client):
        """Test clearing history"""
        memory = ConversationMemory(redis_client, tenant_id=1)
        user_id = 123
        await memory.add_message(user_id, {"role": "user", "content": "Test"})

        await memory.clear(user_id)

        history = await memory.get_history(user_id)
        assert len(history) == 0

    async def test_tenant_isolation(self, redis_client):
        """Test that different tenants have isolated history"""
        mem1 = ConversationMemory(redis_client, tenant_id=1)
        mem2 = ConversationMemory(redis_client, tenant_id=2)
        user_id = 123

        await mem1.add_message(user_id, {"role": "user", "content": "Tenant 1 message"})
        await mem2.add_message(user_id, {"role": "user", "content": "Tenant 2 message"})

        h1 = await mem1.get_history(user_id)
        h2 = await mem2.get_history(user_id)

        assert len(h1) == 1
        assert h1[0]["content"] == "Tenant 1 message"
        assert len(h2) == 1
        assert h2[0]["content"] == "Tenant 2 message"

    async def test_user_isolation(self, redis_client):
        """Test that different users have isolated history"""
        memory = ConversationMemory(redis_client, tenant_id=1)
        u1 = 123
        u2 = 456

        await memory.add_message(u1, {"role": "user", "content": "U1 message"})
        await memory.add_message(u2, {"role": "user", "content": "U2 message"})

        h1 = await memory.get_history(u1)
        h2 = await memory.get_history(u2)

        assert len(h1) == 1
        assert h1[0]["content"] == "U1 message"
        assert len(h2) == 1
        assert h2[0]["content"] == "U2 message"

    async def test_get_history_limit(self, redis_client):
        """Test history retrieval with limit"""
        memory = ConversationMemory(redis_client, tenant_id=1)
        user_id = 123
        for i in range(10):
            await memory.add_message(user_id, {"role": "user", "content": f"msg {i}"})

        history = await memory.get_history(user_id, limit=5)
        assert len(history) == 5
        # Should be the most RECENT 5 messages
        assert history[0]["content"] == "msg 5"
        assert history[4]["content"] == "msg 9"
