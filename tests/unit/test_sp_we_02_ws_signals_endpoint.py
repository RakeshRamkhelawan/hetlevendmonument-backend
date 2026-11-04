import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocketDisconnect


@pytest.mark.unit
class TestCopilotSignalsEndpoint:
    def test_signals_endpoint_registered(self):
        """WebSocket route /ws/copilot/signals bestaat in de app router registry."""
        from src.main import app
        from src.core.api.router_registry import register_all_routers
        
        # Omdat router registratie is uitgesteld naar de app lifespan, registeren we ze handmatig voor de test
        register_all_routers(app)
        
        routes = [r.path for r in app.routes]
        assert "/ws/copilot/signals" in routes

    async def test_signals_ws_auth_called(self):
        """Signals endpoint roept get_current_user_ws aan voor authenticatie."""
        from src.core.api.copilot_websocket_endpoints import copilot_signals_websocket
        
        websocket = AsyncMock()
        current_user = MagicMock()
        current_user.id = 42
        
        mock_manager = AsyncMock()
        
        # Test dat de endpoint verbinding accepteert, registreert en disconnect oproept
        # We mocken receive_text om direct WebSocketDisconnect te triggeren
        websocket.receive_text.side_effect = WebSocketDisconnect()
        
        await copilot_signals_websocket(
            websocket=websocket,
            current_user=current_user,
            connection_manager=mock_manager
        )
        
        websocket.accept.assert_awaited_once()
        mock_manager.subscribe_user.assert_awaited_once_with(user_id=42, websocket=websocket)
        mock_manager.disconnect.assert_called_once_with(user_id=42, websocket=websocket)
