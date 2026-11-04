"""
Unit tests for HITL Notifier Service.

Tests cover:
- Happy path: successful notification broadcast
- Unhappy paths: ticket not found, broadcast failure
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.tool_broker.hitl_notifier import (
    notify_new_ticket,
    notify_ticket_approved,
    notify_ticket_rejected,
)


class TestHITLNotifierHappyPath:
    """Happy path tests for HITL notifier."""

    @pytest.mark.asyncio
    async def test_notify_new_ticket_success(self):
        """Test successful notification of new ticket."""
        mock_ticket = {
            "ticket_ref": "TOOL-A1B2C3D4",
            "status": "pending",
            "tenant_id": 1,
            "agent_id": "agent-001",
        }

        with patch(
            "src.core.tool_broker.hitl_notifier.get_ticket_async",
            return_value=mock_ticket,
        ):
            with patch(
                "src.core.tool_broker.hitl_notifier.connection_manager",
            ) as mock_cm:
                mock_cm.broadcast_to_channel = AsyncMock(return_value=3)

                result = await notify_new_ticket("TOOL-A1B2C3D4", 1, AsyncMock())

                assert result is True
                mock_cm.broadcast_to_channel.assert_called_once()
                call_args = mock_cm.broadcast_to_channel.call_args
                assert call_args[0][0] == "hitl:1"  # channel
                assert call_args[0][1]["type"] == "hitl:new"
                assert call_args[0][1]["ticket_ref"] == "TOOL-A1B2C3D4"
                assert "timestamp" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_notify_ticket_approved_success(self):
        """Test successful notification of ticket approval."""
        mock_ticket = {
            "ticket_ref": "TOOL-A1B2C3D4",
            "status": "approved",
            "tenant_id": 1,
            "agent_id": "agent-001",
        }

        with patch(
            "src.core.tool_broker.hitl_notifier.get_ticket_async",
            return_value=mock_ticket,
        ):
            with patch(
                "src.core.tool_broker.hitl_notifier.connection_manager",
            ) as mock_cm:
                mock_cm.broadcast_to_channel = AsyncMock(return_value=2)

                result = await notify_ticket_approved(
                    "TOOL-A1B2C3D4", 1, "admin@example.com", AsyncMock()
                )

                assert result is True
                mock_cm.broadcast_to_channel.assert_called_once()
                call_args = mock_cm.broadcast_to_channel.call_args
                assert call_args[0][0] == "hitl:1"
                assert call_args[0][1]["type"] == "hitl:approved"

    @pytest.mark.asyncio
    async def test_notify_ticket_rejected_success(self):
        """Test successful notification of ticket rejection."""
        mock_ticket = {
            "ticket_ref": "TOOL-A1B2C3D4",
            "status": "rejected",
            "tenant_id": 1,
            "agent_id": "agent-001",
        }

        with patch(
            "src.core.tool_broker.hitl_notifier.get_ticket_async",
            return_value=mock_ticket,
        ):
            with patch(
                "src.core.tool_broker.hitl_notifier.connection_manager",
            ) as mock_cm:
                mock_cm.broadcast_to_channel = AsyncMock(return_value=1)

                result = await notify_ticket_rejected(
                    "TOOL-A1B2C3D4", 1, "admin@example.com", AsyncMock()
                )

                assert result is True
                mock_cm.broadcast_to_channel.assert_called_once()
                call_args = mock_cm.broadcast_to_channel.call_args
                assert call_args[0][0] == "hitl:1"
                assert call_args[0][1]["type"] == "hitl:rejected"


class TestHITLNotifierUnhappyPath:
    """Unhappy path tests for HITL notifier."""

    @pytest.mark.asyncio
    async def test_notify_new_ticket_not_found(self):
        """Test notification when ticket doesn't exist."""
        with patch(
            "src.core.tool_broker.hitl_notifier.get_ticket_async",
            return_value=None,
        ):
            with patch(
                "src.core.tool_broker.hitl_notifier.connection_manager",
            ) as mock_cm:
                mock_cm.broadcast_to_channel = AsyncMock()

                result = await notify_new_ticket("TOOL-NOTFOUND", 1, AsyncMock())

                assert result is False
                mock_cm.broadcast_to_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_ticket_approved_not_found(self):
        """Test approval notification when ticket doesn't exist."""
        with patch(
            "src.core.tool_broker.hitl_notifier.get_ticket_async",
            return_value=None,
        ):
            with patch(
                "src.core.tool_broker.hitl_notifier.connection_manager",
            ) as mock_cm:
                mock_cm.broadcast_to_channel = AsyncMock()

                result = await notify_ticket_approved(
                    "TOOL-NOTFOUND", 1, "admin@example.com", AsyncMock()
                )

                assert result is False
                mock_cm.broadcast_to_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_ticket_rejected_not_found(self):
        """Test rejection notification when ticket doesn't exist."""
        with patch(
            "src.core.tool_broker.hitl_notifier.get_ticket_async",
            return_value=None,
        ):
            with patch(
                "src.core.tool_broker.hitl_notifier.connection_manager",
            ) as mock_cm:
                mock_cm.broadcast_to_channel = AsyncMock()

                result = await notify_ticket_rejected(
                    "TOOL-NOTFOUND", 1, "admin@example.com", AsyncMock()
                )

                assert result is False
                mock_cm.broadcast_to_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_new_ticket_broadcast_failure(self):
        """Test notification when broadcast fails."""
        mock_ticket = {
            "ticket_ref": "TOOL-A1B2C3D4",
            "status": "pending",
            "tenant_id": 1,
        }

        with patch(
            "src.core.tool_broker.hitl_notifier.get_ticket_async",
            return_value=mock_ticket,
        ):
            with patch(
                "src.core.tool_broker.hitl_notifier.connection_manager",
            ) as mock_cm:
                mock_cm.broadcast_to_channel = AsyncMock(side_effect=Exception("Connection failed"))

                result = await notify_new_ticket("TOOL-A1B2C3D4", 1, AsyncMock())

                assert result is False


class TestHITLNotifierMessageFormat:
    """Tests for notification message format."""

    @pytest.mark.asyncio
    async def test_message_contains_required_fields(self):
        """Test that notification messages contain all required fields."""
        mock_ticket = {
            "ticket_ref": "TOOL-A1B2C3D4",
            "status": "pending",
            "tenant_id": 1,
            "agent_id": "agent-001",
            "tool_name": "test_tool",
        }

        with patch(
            "src.core.tool_broker.hitl_notifier.get_ticket_async",
            return_value=mock_ticket,
        ):
            with patch(
                "src.core.tool_broker.hitl_notifier.connection_manager",
            ) as mock_cm:
                mock_cm.broadcast_to_channel = AsyncMock(return_value=1)

                await notify_new_ticket("TOOL-A1B2C3D4", 1, AsyncMock())

                call_args = mock_cm.broadcast_to_channel.call_args
                message = call_args[0][1]

                # Check required fields
                assert "type" in message
                assert "ticket_ref" in message
                assert "data" in message
                assert "timestamp" in message

                # Check data contains ticket info
                assert message["data"]["ticket_ref"] == "TOOL-A1B2C3D4"
                assert message["data"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_timestamp_is_iso_format(self):
        """Test that timestamp is in ISO format."""
        mock_ticket = {"ticket_ref": "TOOL-A1B2C3D4", "status": "pending"}

        with patch(
            "src.core.tool_broker.hitl_notifier.get_ticket_async",
            return_value=mock_ticket,
        ):
            with patch(
                "src.core.tool_broker.hitl_notifier.connection_manager",
            ) as mock_cm:
                mock_cm.broadcast_to_channel = AsyncMock(return_value=1)

                await notify_new_ticket("TOOL-A1B2C3D4", 1, AsyncMock())

                call_args = mock_cm.broadcast_to_channel.call_args
                message = call_args[0][1]
                timestamp = message["timestamp"]

                # Should be parseable as ISO format
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                assert parsed.tzinfo is not None


PII_IN_A_SHELL_COMMAND = "curl -d 'bsn=123456782' https://intern.example/api"


@pytest.mark.unit
class TestTheBroadcastCarriesNoRawToolInput:
    """De websocket-uitzending mag het onbewerkte `tool_input` niet bevatten (ADR-036 OP-58).

    **Waarom dit los van de rolcheck op de endpoints moet.** `/hitl/pending` en `/hitl/audit`
    hebben sinds OP-56 een beheerdersrol nodig, en dat is de HTTP-deur. Maar alle drie de
    notify-functies zetten het VOLLEDIGE ticket -- inclusief het onbewerkte `tool_input` uit
    `hitl_store.get_ticket_async` -- in `message["data"]` en zenden dat naar kanaal
    `hitl:{tenant_id}`. Dat kanaal wordt geserveerd door `/ws/hitl/{tenant_id}`
    (`api/v1/websocket_hitl.py`), en de enige controle daar is `user.tenant_id != tenant_id`:
    GEEN rolcheck.

    Gevolg: elke ingelogde gebruiker van de tenant met een open websocket ontving bij elke
    goedkeuring het shell-commando of de e-mailtekst die de agent wilde uitvoeren. De rolcheck
    beschermde de deur terwijl het raam openstond.

    Gevonden door de Taak 2-review, en het is de reden dat de route-fix (OP-37) en het opruimen van
    de payload in dezelfde reeks moeten: de route aanbieden zonder dit maakt de situatie ERGER dan
    ervoor. Zonder gemounte route werd er nooit goedgekeurd en lekte er niets.

    De client heeft dit niet nodig: `ticket_ref` plus `status` is genoeg om te weten dat er iets
    veranderd is, en de rest hoort hij op te halen via het endpoint dat wel een rolcheck heeft.
    """

    #: Zoals `hitl_store._to_dict` hem echt oplevert. De eerdere versie miste `reason` en
    #: `requested_by`, en juist daardoor kon deze test niet zien dat de uitsluitlijst te smal was
    #: (ADR-036 OP-66): `reason` is `payload["_reason"]`, oftewel `decision.explanation_for_user`
    #: -- door het model geschreven proza dat de handeling beschrijft en de parameters navertelt.
    TICKET = {
        "ticket_ref": "TOOL-LEAK1234",
        "status": "pending",
        "tenant_id": 1,
        "agent_id": "agent-001",
        "tool_name": "local__run_shell",
        "tool_input": {"command": PII_IN_A_SHELL_COMMAND},
        "reason": f"Deze actie vereist goedkeuring: {PII_IN_A_SHELL_COMMAND}",
        "requested_by": "aanvrager@tenant.nl",
        "task_id": "taak-1",
    }

    @staticmethod
    def _broadcast_message(mock_cm: MagicMock) -> dict:
        mock_cm.broadcast_to_channel.assert_called_once()
        return mock_cm.broadcast_to_channel.call_args[0][1]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "notify,args",
        [
            (notify_new_ticket, ()),
            (notify_ticket_approved, ("user:42",)),
            (notify_ticket_rejected, ("user:42",)),
        ],
    )
    async def test_no_notification_broadcasts_the_raw_tool_input(self, notify, args):
        with patch(
            "src.core.tool_broker.hitl_notifier.get_ticket_async",
            return_value=dict(self.TICKET),
        ):
            with patch("src.core.tool_broker.hitl_notifier.connection_manager") as mock_cm:
                mock_cm.broadcast_to_channel = AsyncMock(return_value=1)

                await notify("TOOL-LEAK1234", 1, *args, AsyncMock())

                message = self._broadcast_message(mock_cm)

        rendered = json.dumps(message, default=str)
        assert PII_IN_A_SHELL_COMMAND not in rendered, (
            f"{notify.__name__} zendt het onbewerkte tool_input naar kanaal hitl:1. Dat kanaal is "
            "voor ELKE ingelogde gebruiker van de tenant leesbaar -- /ws/hitl/{tenant_id} toetst "
            "alleen de tenant, geen rol. Stuur ticket_ref en status; de client haalt de rest op via "
            "het endpoint met de rolcheck."
        )
        assert "tool_input" not in rendered, (
            f"{notify.__name__} zendt de sleutel `tool_input` mee. Ook een lege of geprojecteerde "
            "variant hoort hier niet: de client mag er niet op gaan vertrouwen."
        )
        for leaky in ("reason", "requested_by", "agent_id", "task_id"):
            assert leaky not in rendered, (
                f"{notify.__name__} zendt `{leaky}` mee over kanaal hitl:1. `reason` is de door het "
                "model geschreven uitleg van de handeling; `requested_by` is het e-mailadres van de "
                "aanvrager. Dat kanaal heeft GEEN rolcheck, dus dit gaat naar elke ingelogde "
                "gebruiker van de tenant. Een uitsluitlijst is hier te smal gebleken -- gebruik een "
                "toelaatlijst."
            )

    @pytest.mark.asyncio
    async def test_the_notification_still_says_which_ticket_changed(self):
        """Vangnet: een leeg bericht zou de test hierboven ook groen maken.

        Zonder deze assertie is "stuur niets" een geldige oplossing, en dan weet de client niet
        meer dat er iets veranderd is -- dan is het HITL-scherm stil kapot.
        """
        with patch(
            "src.core.tool_broker.hitl_notifier.get_ticket_async",
            return_value=dict(self.TICKET),
        ):
            with patch("src.core.tool_broker.hitl_notifier.connection_manager") as mock_cm:
                mock_cm.broadcast_to_channel = AsyncMock(return_value=1)

                await notify_ticket_approved("TOOL-LEAK1234", 1, "user:42", AsyncMock())

                message = self._broadcast_message(mock_cm)

        assert message["ticket_ref"] == "TOOL-LEAK1234"
        assert message["type"] == "hitl:approved"
        assert "timestamp" in message
