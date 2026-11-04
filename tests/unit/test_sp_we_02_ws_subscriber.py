import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
class TestConnectionManagerSubscriber:
    async def test_subscribe_registers_websocket(self):
        """subscribe_user() registreert de WS bij de juiste user_id."""
        from src.core.websocket.manager import ConnectionManager
        manager = ConnectionManager(redis_client=None)
        ws = AsyncMock()
        await manager.subscribe_user(user_id=42, websocket=ws)
        assert 42 in manager._subscriptions
        assert ws in manager._subscriptions[42]

    async def test_unsubscribe_removes_websocket(self):
        """disconnect() verwijdert de WS uit subscriptions."""
        from src.core.websocket.manager import ConnectionManager
        manager = ConnectionManager(redis_client=None)
        ws = AsyncMock()
        await manager.subscribe_user(user_id=42, websocket=ws)
        await manager.disconnect(user_id=42, websocket=ws)
        assert 42 not in manager._subscriptions or ws not in manager._subscriptions.get(42, [])

    async def test_on_redis_message_sends_to_websocket(self):
        """Redis-bericht wordt doorgestuurd naar verbonden WebSocket."""
        from src.core.websocket.manager import ConnectionManager
        ws = AsyncMock()
        manager = ConnectionManager(redis_client=None)
        await manager.subscribe_user(user_id=42, websocket=ws)
        await manager.on_redis_message(user_id=42, message='{"type":"SIGNAL"}')
        ws.send_text.assert_awaited_once_with('{"type":"SIGNAL"}')

    async def test_on_redis_message_skips_disconnected(self):
        """Bericht naar niet-verbonden user_id gooit geen exception."""
        from src.core.websocket.manager import ConnectionManager
        manager = ConnectionManager(redis_client=None)
        # user_id=99 is niet gesubscribed
        await manager.on_redis_message(user_id=99, message='{"type":"SIGNAL"}')
        # geen exception

    async def test_redis_subscription_cleanup_on_exception(self):
        """Kapotte WebSocket wordt verwijderd uit subscriptions."""
        from src.core.websocket.manager import ConnectionManager
        ws = AsyncMock()
        ws.send_text.side_effect = Exception("WebSocket closed")
        manager = ConnectionManager(redis_client=None)
        await manager.subscribe_user(user_id=42, websocket=ws)
        await manager.on_redis_message(user_id=42, message='{"type":"SIGNAL"}')
        assert ws not in manager._subscriptions.get(42, [])

    async def test_redis_listener_flow(self):
        """Test dat de redis listener daadwerkelijk berichten ophaalt en doorstuurt."""
        from src.core.websocket.manager import ConnectionManager
        mock_redis = MagicMock()
        mock_pubsub = MagicMock()  # MagicMock so listen() doesn't return a coroutine
        mock_redis.pubsub.return_value = mock_pubsub
        
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        
        async def mock_listen():
            yield {"type": "message", "data": b'{"type":"SIGNAL_BYTES"}'}
            # Geef asyncio de kans om te stoppen
            await asyncio.sleep(0.01)
            
        mock_pubsub.listen = mock_listen
        
        manager = ConnectionManager(redis_client=mock_redis)
        ws = AsyncMock()
        await manager.subscribe_user(user_id=42, websocket=ws)
        
        # Geef event loop tijd om de achtergrond listener taak te draaien
        await asyncio.sleep(0.05)
        
        # Verifieer dat ws.send_text is aangeroepen met de data
        ws.send_text.assert_awaited_with('{"type":"SIGNAL_BYTES"}')
        
        # Cleanup
        await manager.disconnect(user_id=42, websocket=ws)
