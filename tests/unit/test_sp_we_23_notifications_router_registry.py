"""
Regression test voor SP-WE-23: notifications router registratie.

Bron: NEW-WIRE-005
Na SP-API-001 Dag 5 (dead code removal) is notificatie-registratie gemigreerd
naar src/core/api/registries/realtime.py (ADR-033 Laag 2 patroon).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestNotificationsRouterRegistryOrder:
    """Verify notifications are registered via the Laag 2 realtime registry."""

    def test_notifications_registered_in_realtime_registry(self) -> None:
        """realtime.py Laag 2 registry must import and register notifications router.

        Na SP-API-001 Dag 5 is _register_notifications_v1 verwijderd uit
        router_registry.py. Registratie gebeurt nu via realtime.register(app).
        """
        src_path = Path("src/core/api/registries/realtime.py")
        source = src_path.read_text(encoding="utf-8")

        assert "notifications" in source, (
            "realtime.py registry must import/register the notifications router"
        )
        assert "register" in source, "realtime.py must define a register() function"

    def test_realtime_register_is_callable_and_returns_int(self) -> None:
        """realtime.register() must accept a FastAPI app and return an int >= 1."""
        from src.core.api.registries.realtime import register

        mock_app = MagicMock()

        with patch("src.core.api.v1.notifications.router.router", MagicMock()):
            with patch("src.core.copilot.api.chat_websocket.router", MagicMock()):
                with patch("src.core.copilot.api.audit_endpoints.router", MagicMock()):
                    with patch.object(mock_app, "include_router"):
                        result = register(mock_app)

        assert isinstance(result, int), f"Expected int return, got {type(result)}"
        assert result >= 1, f"Expected at least 1 router registered, got {result}"
