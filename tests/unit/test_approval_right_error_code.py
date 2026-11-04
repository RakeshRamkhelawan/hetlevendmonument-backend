"""De weigering van een goedkeuring draagt een foutCODE, niet alleen een Engelse tekst.

Aanleiding (acceptatie derde ronde, 2026-10-10): na het intrekken van de rol Goedkeurder toonde
/hitl de Engelse backendregel "Approving or rejecting a HITL request requires an approval right".
Het scherm moet op een code kunnen vertrouwen en zelf Nederlands tonen.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest

from src.core.auth import approval_rights
from src.core.exceptions import SanskritiError


@pytest.fixture
def zonder_recht() -> Iterator[AsyncMock]:
    with patch.object(approval_rights, "has_approval_right", AsyncMock(return_value=False)) as m:
        yield m


@pytest.mark.usefixtures("zonder_recht")
class TestDeWeigeringDraagtEenCode:
    async def test_the_list_refusal_has_the_code(self) -> None:
        with pytest.raises(SanskritiError) as fout:
            await approval_rights.require_any_approval_right(AsyncMock(), AsyncMock())

        assert fout.value.error_code == "APPROVAL_RIGHT_REQUIRED"

    async def test_the_tool_refusal_has_the_code(self) -> None:
        with pytest.raises(SanskritiError) as fout:
            await approval_rights.require_approval_right_for_tool(
                AsyncMock(), AsyncMock(), "send_payment_reminder"
            )

        assert fout.value.error_code == "APPROVAL_RIGHT_REQUIRED"

    async def test_the_agent_refusal_has_the_code(self) -> None:
        with pytest.raises(SanskritiError) as fout:
            await approval_rights.require_approval_right_for_agent(
                AsyncMock(), AsyncMock(), "dunning"
            )

        assert fout.value.error_code == "APPROVAL_RIGHT_REQUIRED"

    async def test_the_refusal_is_a_403(self) -> None:
        with pytest.raises(SanskritiError) as fout:
            await approval_rights.require_any_approval_right(AsyncMock(), AsyncMock())

        assert fout.value.status_code == 403

    async def test_the_refusal_message_is_not_the_old_english_technical_text(self) -> None:
        with pytest.raises(SanskritiError) as fout:
            await approval_rights.require_any_approval_right(AsyncMock(), AsyncMock())

        assert "requires an approval right" not in fout.value.message
