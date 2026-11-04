"""Debiteurenagent dag 3: de naam van de ontvanger in de brief, en een rijslot bij versturen.

1. `recipient_name` staat in de parameters van `send_payment_reminder`, zodat de goedkeurkaart
   AAN WIE toont zonder tweede databron; de tool vergelijkt hem bij uitvoeren net als de tekst.
2. Tussen de controle "is deze factuur al betaald?" en het schrijven mag niemand de rij wijzigen.
   Het verstuurpad leest de factuur daarom met `SELECT ... FOR UPDATE`. SQLite laat die clausule
   weg bij het compileren, dus deze test meet het op het statement-object (`_for_update_arg`).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from tests.unit.tool_broker.test_receivables_registry import VERSTUREN, _brief, _registry, _seed


@pytest.mark.unit
@pytest.mark.asyncio
class TestNaamVanDeOntvanger:
    async def test_the_preview_carries_the_name_of_the_recipient(
        self, db_session: AsyncSession
    ) -> None:
        rid = await _seed(db_session, 1, "a", "A-1")

        params = await _brief(db_session, 1, rid)

        assert params["recipient_name"] == "Klant a"

    async def test_a_changed_name_is_refused(self, db_session: AsyncSession) -> None:
        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid)
        params["recipient_name"] = "Iemand anders"

        uit = await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_n1"}, tenant_id=1
        )

        assert uit["success"] is False


@pytest.mark.unit
@pytest.mark.asyncio
class TestRijslot:
    async def test_the_send_path_locks_the_receivable_row(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rid = await _seed(db_session, 1, "a", "A-1")
        params = await _brief(db_session, 1, rid)
        statements: list[Any] = []
        echt = db_session.execute

        async def opnemen(statement: Any, *args: Any, **kwargs: Any) -> Any:
            statements.append(statement)
            return await echt(statement, *args, **kwargs)

        monkeypatch.setattr(db_session, "execute", opnemen)

        await _registry(db_session).execute_receivables_tool(
            VERSTUREN, {**params, "_hitl_ticket_ref": "hitl_l1"}, tenant_id=1
        )

        vergrendeld = [
            s for s in statements if isinstance(s, Select) and s._for_update_arg is not None
        ]
        assert len(vergrendeld) == 1
